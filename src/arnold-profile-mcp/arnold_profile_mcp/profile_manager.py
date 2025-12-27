"""Profile management business logic for Arnold."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Any


PROFILE_PATH = Path("/Users/brock/Documents/GitHub/arnold/data/profile.json")


class ProfileManager:
    """Manages user profile creation, retrieval, and updates."""

    def create_profile(
        self,
        name: str,
        age: int,
        sex: str,
        height_inches: Optional[float] = None,
        birth_date: Optional[str] = None,
        time_zone: str = "America/New_York"
    ) -> dict:
        """
        Create new profile and save to JSON.

        Args:
            name: User's name
            age: User's age
            sex: Biological sex (male/female/other)
            height_inches: Height in inches (optional)
            birth_date: Birth date YYYY-MM-DD (optional)
            time_zone: User's time zone

        Returns:
            Created profile dictionary

        Raises:
            ValueError: If profile already exists
        """
        # Check if profile already exists
        if PROFILE_PATH.exists():
            raise ValueError("Profile already exists. Use update_profile to modify.")

        # Generate UUID
        person_id = str(uuid.uuid4())

        # Build profile
        profile = {
            "person_id": person_id,
            "created_at": datetime.now().isoformat(),
            "demographics": {
                "name": name,
                "age": age,
                "sex": sex,
                "height_inches": height_inches,
                "birth_date": birth_date
            },
            "check_in": {
                "last_check_in": None,
                "frequency_days": 14,
                "next_reminder": None
            },
            "exercise_aliases": {},
            "preferences": {
                "default_units": "imperial",
                "communication_style": "direct",
                "time_zone": time_zone
            },
            "neo4j_refs": {
                "current_primary_equipment_inventory": None
            }
        }

        # Ensure /data directory exists
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Write to JSON
        with open(PROFILE_PATH, 'w') as f:
            json.dump(profile, f, indent=2)

        return profile

    def get_profile(self) -> dict:
        """
        Load profile from JSON.

        Returns:
            Profile dictionary

        Raises:
            FileNotFoundError: If profile doesn't exist
        """
        if not PROFILE_PATH.exists():
            raise FileNotFoundError("Profile not found. Run create_profile first.")

        with open(PROFILE_PATH, 'r') as f:
            return json.load(f)

    def update_profile(self, field_path: str, value: Any) -> dict:
        """
        Update specific field using dot notation.

        Args:
            field_path: Dot-notation path (e.g., "demographics.age")
            value: New value for the field

        Returns:
            Updated profile dictionary

        Raises:
            KeyError: If field path is invalid
        """
        profile = self.get_profile()

        # Parse field path (e.g., "demographics.age")
        keys = field_path.split('.')

        # Navigate to parent
        current = profile
        for key in keys[:-1]:
            if key not in current:
                raise KeyError(f"Invalid field path: {field_path}")
            current = current[key]

        # Update final key
        final_key = keys[-1]
        if final_key not in current:
            raise KeyError(f"Invalid field path: {field_path}")

        current[final_key] = value

        # Save
        with open(PROFILE_PATH, 'w') as f:
            json.dump(profile, f, indent=2)

        return profile

    def profile_exists(self) -> bool:
        """Check if profile file exists."""
        return PROFILE_PATH.exists()

    def parse_intake_response(self, response_text: str) -> dict:
        """
        Parse user's intake questionnaire response into structured data.

        Args:
            response_text: User's freeform response to intake questions

        Returns:
            Dictionary with parsed profile fields

        Raises:
            ValueError: If required fields are missing
        """
        import re

        result = {}

        # Extract name (required)
        name_match = re.search(r'Name:\s*(.+?)(?:\n|$)', response_text, re.IGNORECASE)
        if name_match:
            result['name'] = name_match.group(1).strip()

        # Extract age (required)
        age_match = re.search(r'Age:\s*(\d+)', response_text, re.IGNORECASE)
        if age_match:
            result['age'] = int(age_match.group(1))

        # Extract sex (required)
        sex_match = re.search(r'(?:Sex|Biological Sex):\s*(male|female|other)', response_text, re.IGNORECASE)
        if sex_match:
            result['sex'] = sex_match.group(1).lower()

        # Extract height (optional)
        height_match = re.search(r'Height:\s*(\d+(?:\.\d+)?)', response_text, re.IGNORECASE)
        if height_match:
            result['height_inches'] = float(height_match.group(1))

        # Extract birth date (optional)
        birthdate_match = re.search(r'Birth Date:\s*(\d{4}-\d{2}-\d{2})', response_text, re.IGNORECASE)
        if birthdate_match:
            result['birth_date'] = birthdate_match.group(1)

        # Extract time zone (optional)
        tz_match = re.search(r'Time Zone:\s*(.+?)(?:\n|$)', response_text, re.IGNORECASE)
        if tz_match:
            result['time_zone'] = tz_match.group(1).strip()

        # Validate required fields
        required = ['name', 'age', 'sex']
        missing = [f for f in required if f not in result]

        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        return result
