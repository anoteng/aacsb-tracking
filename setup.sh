#!/bin/bash
# AACSB Application Setup Script

set -e

echo "Setting up AACSB Accreditation Application..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo ./setup.sh)"
    exit 1
fi

cd /var/www/aacsb

# Create Python virtual environment
echo "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r backend/requirements.txt

# Create .env file if it doesn't exist
if [ ! -f backend/.env ]; then
    echo "Creating .env file..."
    cp backend/.env.example backend/.env
    # Generate a secure secret key
    SECRET_KEY=$(openssl rand -hex 32)
    sed -i "s/change-this-in-production/$SECRET_KEY/" backend/.env
    echo "Please edit backend/.env to set your database password and other settings"
fi

# Set permissions
echo "Setting permissions..."
chown -R www-data:www-data /var/www/aacsb
chmod -R 755 /var/www/aacsb

# Install systemd service
echo "Installing systemd service..."
cp aacsb.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable aacsb

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit /var/www/aacsb/backend/.env with your database password"
echo "2. Add the NGINX configuration from nginx.conf to your server block"
echo "3. Test NGINX config: nginx -t"
echo "4. Reload NGINX: systemctl reload nginx"
echo "5. Start the application: systemctl start aacsb"
echo "6. Check status: systemctl status aacsb"
echo ""
echo "To create your admin user, run:"
echo "  mysql -u aol -p aol"
echo "  INSERT INTO users (firstname, lastname, email) VALUES ('Your', 'Name', 'your.email@nmbu.no');"
echo "  INSERT INTO user_roles (role_id, uuid) SELECT 1, uuid FROM users WHERE email='your.email@nmbu.no';"
echo ""
