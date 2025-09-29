-- Create database
CREATE DATABASE IF NOT EXISTS kiosk_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create user
CREATE USER IF NOT EXISTS 'kiosk_user'@'localhost' IDENTIFIED BY 'kiosk_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON kiosk_db.* TO 'kiosk_user'@'localhost';
FLUSH PRIVILEGES; 