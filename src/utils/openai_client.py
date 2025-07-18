import os
import openai
from typing import Dict, List, Optional
import json
import re
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
current_dir = Path(__file__).parent
src_dir = current_dir.parent
project_dir = src_dir.parent
env_file = project_dir / '.env'
load_dotenv(env_file)

class OpenAIClient:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("Missing OPENAI_API_KEY environment variable")
        
        self.client = openai.OpenAI(api_key=api_key)
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        
    def extract_referral_info(self, message: str) -> List[Dict]:
        """Extract referral information from tenant messages"""
        
        system_prompt = """You are extracting referral information from tenant messages.

    Look for:
    - Names of potential referrals
    - Phone numbers  
    - Email addresses

    Extract referral information from this message: "{}"

    IMPORTANT: Return ONLY a valid JSON array. No other text.

    Format: [{{"name": "Name", "phone": "+1234567890", "email": "email@example.com", "notes": "context"}}]

    If no referrals found, return: []

    Examples:
    Message: "My friend Sarah is looking for a place. Her number is 555-1234"
    Response: [{{"name": "Sarah", "phone": "+15551234", "email": "", "notes": "friend of tenant"}}]

    Message: "Nobody I can think of"
    Response: []
    """.format(message)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract referral info from: {message}"}
                ],
                max_tokens=300,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            
            # Debug: print the raw response
            print(f"Raw OpenAI response: {content}")
            
            # Try to parse JSON
            try:
                referral_info = json.loads(content)
            except json.JSONDecodeError:
                # If JSON parsing fails, try to extract JSON from the response
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    referral_info = json.loads(json_match.group())
                else:
                    print(f"Could not parse JSON from: {content}")
                    return []
            
            # Clean and validate referral info
            cleaned_referrals = []
            for referral in referral_info:
                if referral.get('name') or referral.get('phone') or referral.get('email'):
                    # Clean phone number format
                    phone = referral.get('phone', '')
                    if phone:
                        # Basic phone number cleaning
                        phone = re.sub(r'[^\d+]', '', phone)
                        if phone and not phone.startswith('+'):
                            phone = '+1' + phone.lstrip('1')
                        referral['phone'] = phone
                    
                    cleaned_referrals.append(referral)
            
            return cleaned_referrals
        
        except Exception as e:
            print(f"Error extracting referral info: {e}")
            return []
    
    def generate_referral_response(self, tenant_data: Dict, incoming_message: str, extracted_referrals: List[Dict] = None) -> str:
        """Generate a conversational response for referral conversations"""
        
        tenant_status = tenant_data.get('status', 'active')
        referrals_provided = tenant_data.get('referrals_provided', 0)
        
        if extracted_referrals:
            # Tenant just provided referral info
            referral_names = [ref.get('name', 'someone') for ref in extracted_referrals]
            
            if len(referral_names) == 1:
                acknowledgment = f"Perfect! Thanks for referring {referral_names[0]}."
            else:
                acknowledgment = f"Awesome! Thanks for referring {', '.join(referral_names)}."
            
            system_prompt = f"""You are a friendly AI assistant collecting referrals from current tenants.

    The tenant just provided referral information. Generate a response that:
    1. Thanks them for the referral(s)
    2. Asks if they know anyone else who might be looking
    3. Keeps it brief and friendly
    4. Uses emojis appropriately

    Start with: "{acknowledgment}"

    The tenant just said: "{incoming_message}"
    """
        else:
            # Regular conversation or follow-up
            system_prompt = f"""You are a friendly AI assistant collecting referrals from current tenants for off-campus housing.

    Generate a conversational response that:
    - Acknowledges their message
    - Encourages them to share referral information if they haven't already
    - Asks for name and phone number of potential referrals
    - Keeps it casual and friendly
    - Uses emojis appropriately
    - If they seem hesitant, reassure them it's just to help their friends find housing

    The tenant just said: "{incoming_message}"
    """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Generate a friendly referral response."}
                ],
                max_tokens=150,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            print(f"Error generating referral response: {e}")
            return "Thanks for your message! Do you know anyone who might be looking for housing?"