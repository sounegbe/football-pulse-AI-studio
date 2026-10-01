"""Local account provisioning; passwords are read without echoing them."""
import argparse
import getpass
import sqlite3
from app.backend.config import Settings
from app.backend.database import Database
from app.backend.security import provision_user

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Provision a local studio account')
    parser.add_argument('command', choices=['create-user'])
    parser.add_argument('username')
    args = parser.parse_args()
    password = getpass.getpass('Password (12–128 characters): ')
    confirmation = getpass.getpass('Confirm password: ')
    if password != confirmation:
        parser.error('Passwords do not match')
    db = Database(Settings.from_env().data_dir)
    db.initialize()
    try:
        provision_user(db, args.username, password)
    except (ValueError, sqlite3.IntegrityError) as exc:
        parser.error(str(exc))
    print('Account created.')
