"""
NVA (Norwegian Research Archive) API integration service.
Documentation: https://api.nva.unit.no/
"""

import httpx
from datetime import datetime, timedelta
from typing import Optional
from config import get_settings

settings = get_settings()


class NVAService:
    def __init__(self):
        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

    async def _get_token(self) -> str:
        """Get OAuth token using client credentials flow."""
        if self._token and self._token_expires and datetime.now() < self._token_expires:
            return self._token

        if not settings.nva_client_id or not settings.nva_client_secret:
            raise ValueError("NVA API credentials not configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.nva_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.nva_client_id,
                    "client_secret": settings.nva_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

            self._token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            self._token_expires = datetime.now() + timedelta(seconds=expires_in - 60)

            return self._token

    async def search_publications(
        self,
        contributor_id: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        institution: str = "nmbu",
        page: int = 0,
        page_size: int = 100,
    ) -> dict:
        """
        Search for publications in NVA.

        Args:
            contributor_id: Cristin person ID
            year_from: Start year for publications
            year_to: End year for publications
            institution: Institution identifier (default: nmbu)
            page: Page number (0-indexed)
            page_size: Number of results per page
        """
        token = await self._get_token()

        params = {
            "size": page_size,
            "from": page * page_size,
        }

        # Build search query using NVA API parameters
        if contributor_id:
            # Use NVA person URL format (not Cristin API URL)
            params["contributor"] = f"https://api.nva.unit.no/cristin/person/{contributor_id}"

        # Note: institution filter disabled - we get all publications by the contributor
        # regardless of institutional affiliation at time of publication

        if year_from:
            params["publication_year_since"] = year_from

        if year_to:
            params["publication_year_before"] = year_to + 1  # API uses "before", so add 1

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{settings.nva_api_url}/search/resources",
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            return response.json()

    async def get_person_publications(
        self,
        person_id: str,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
    ) -> list[dict]:
        """
        Get all publications for a specific person.

        Args:
            person_id: Cristin person ID
            year_from: Start year (default: 6 years ago)
            year_to: End year (default: 2025)
        """
        # Use 2025 as reference year
        reference_year = 2025
        if not year_from:
            year_from = reference_year - 6
        if not year_to:
            year_to = reference_year

        all_publications = []
        page = 0
        page_size = 100

        while True:
            result = await self.search_publications(
                contributor_id=person_id,
                year_from=year_from,
                year_to=year_to,
                page=page,
                page_size=page_size,
            )

            hits = result.get("hits", [])
            all_publications.extend(hits)

            total = result.get("totalHits", 0)
            if len(all_publications) >= total or len(hits) < page_size:
                break

            page += 1

        return all_publications

    async def get_publication(self, publication_id: str) -> dict:
        """Get details for a specific publication."""
        token = await self._get_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.nva_api_url}/publication/{publication_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            return response.json()

    def parse_publication(self, pub: dict) -> dict:
        """Parse NVA publication data into a simplified format."""
        entity = pub.get("entityDescription", {})
        ref = entity.get("reference", {})
        pub_context = ref.get("publicationContext", {})
        pub_instance = ref.get("publicationInstance", {})

        # Get contributors
        contributors = []
        for contrib in entity.get("contributors", []):
            identity = contrib.get("identity", {})
            contributors.append({
                "name": identity.get("name", "Unknown"),
                "id": identity.get("id"),
                "role": contrib.get("role", {}).get("type"),
            })

        # Get publication date
        pub_date = entity.get("publicationDate", {})
        year = pub_date.get("year")

        # Determine publication type
        pub_type = pub_instance.get("type", "Unknown")
        if "Journal" in pub_type:
            pub_type = "Journal Article"
        elif "Book" in pub_type:
            pub_type = "Book/Chapter"
        elif "Report" in pub_type:
            pub_type = "Report"
        elif "Degree" in pub_type:
            pub_type = "Thesis"

        # Get journal/publisher info
        journal = None
        publisher = None
        if "journal" in pub_context:
            journal = pub_context["journal"].get("name")
        if "publisher" in pub_context:
            publisher = pub_context["publisher"].get("name")

        return {
            "id": pub.get("identifier"),
            "title": entity.get("mainTitle", "Untitled"),
            "type": pub_type,
            "year": year,
            "contributors": contributors,
            "journal": journal,
            "publisher": publisher,
            "doi": pub.get("doi"),
            "nva_url": f"https://nva.sikt.no/registration/{pub.get('identifier')}",
        }


# Singleton instance
nva_service = NVAService()
