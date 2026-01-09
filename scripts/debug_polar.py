#!/usr/bin/env python3
"""Debug Polar API connectivity."""
import os
import requests
from dotenv import load_dotenv

load_dotenv('/Users/brock/Documents/GitHub/arnold/.env')

token = os.environ.get('POLAR_ACCESS_TOKEN')
user_id = os.environ.get('POLAR_USER_ID')

print(f'Token: {token[:20]}...' if token else 'No token')
print(f'User ID: {user_id}')

headers = {'Authorization': f'Bearer {token}'}

print('\n--- Exercises endpoint ---')
r = requests.get('https://www.polaraccesslink.com/v3/exercises', headers=headers)
print(f'Status: {r.status_code}')
print(f'Response: {r.text[:500] if r.text else "(empty)"}')

print('\n--- User info endpoint ---')
r2 = requests.get(f'https://www.polaraccesslink.com/v3/users/{user_id}', headers=headers)
print(f'Status: {r2.status_code}')
print(f'Response: {r2.text[:500] if r2.text else "(empty)"}')
