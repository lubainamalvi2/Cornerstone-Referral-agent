import os
from dotenv import load_dotenv
load_dotenv('../.env')

import json
from typing import Dict, Any

# Import utility classes
from utils.supabase_client import SupabaseClient
from utils.openai_client import OpenAIClient
from utils.telnyx_client import TelnyxClient

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for referral assistant
    """
    try:
        # Parse the incoming webhook
        body = json.loads(event.get('body', '{}'))
        webhook_data = body.get('data', {})
        
        if webhook_data.get('event_type') != 'message.received':
            return {'statusCode': 200, 'body': 'Event ignored'}
        
        # Extract message details
        payload = webhook_data.get('payload', {})
        from_number = payload.get('from', {}).get('phone_number')
        message_text = payload.get('text')
        
        # Process the referral conversation
        response = process_referral_conversation(from_number, message_text)
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Referral processed', 'response': response})
        }
        
    except Exception as e:
        print(f"Error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}

def process_referral_conversation(tenant_phone: str, message: str) -> str:
    """
    Process a message from a tenant about referrals
    """
    try:
        # Initialize clients
        supabase_client = SupabaseClient()
        openai_client = OpenAIClient()
        telnyx_client = TelnyxClient()
        
        # Get tenant info
        tenant = supabase_client.get_tenant_by_phone(tenant_phone)
        
        if not tenant:
            # Unknown tenant - might be a referral response
            return "Thanks for your message! I'll have our team follow up." 
        
        # Check if tenant is declining
        if is_declining(message):
            supabase_client.update_tenant_status(tenant_phone, "declined")
            return "No worries! Thanks for letting me know. Have a great day!"
        
        # Extract referral info from message
        referral_info = openai_client.extract_referral_info(message)
        
        # If they provided referral info, add to leads
        if referral_info:
            for referral in referral_info:
                supabase_client.create_referral_lead(referral, tenant_phone)
        
        # Generate response
        ai_response = openai_client.generate_referral_response(tenant, message, referral_info)
        
        # Send response
        telnyx_client.send_sms(tenant_phone, ai_response)
        
        # Update conversation history
        supabase_client.add_tenant_message(tenant_phone, message, "tenant")
        supabase_client.add_tenant_message(tenant_phone, ai_response, "ai")
        
        return ai_response
        
    except Exception as e:
        print(f"Error processing referral: {e}")
        return "Thanks for your message! I'll have our team follow up."

def is_declining(message: str) -> bool:
    """
    Check if tenant is declining to provide referrals
    """
    message_lower = message.lower().strip()
    
    # Positive indicators (if these exist, probably not declining)
    positive_indicators = [
        'i know', 'yes', 'yeah', 'sure', 'friend', 'someone',
        'looking', 'interested', 'might', 'could', 'name is',
        'number is', 'phone', 'contact', 'email'
    ]
    
    # Check for positive indicators first
    for indicator in positive_indicators:
        if indicator in message_lower:
            return False
    
    # Decline patterns (only check if no positive indicators)
    decline_patterns = [
        'no', 'nope', 'not really', 'nobody', 'not interested',
        'don\'t know anyone', 'dont know anyone', 'no one',
        'not right now', 'not at the moment', 'can\'t think of anyone'
    ]
    
    return any(pattern in message_lower for pattern in decline_patterns)

def send_referral_blast():
    """
    Send referral request to eligible tenants
    """
    try:
        supabase_client = SupabaseClient()
        telnyx_client = TelnyxClient()
        
        # get tenants that are elgiible for blast (they havent been contacted in 30 days)
        eligible_tenants = supabase_client.get_tenants_for_blast(days_since_last_contact = 30)
        if not eligible_tenants:
            print("No eigible tenants for blast.")
            return
        
        #referral blast message
        blast_message = """Hi! This is the AI assistant from Cornerstone Real Estate.
We're looking to help more students find great off-campus housing like yours!
Do you know anyone who might be looking for a place to live? If so, I'd love to get their contact info and help them find something perfect.
Just reply with their name and phone number, or let me know if you don't have any referrals right now. Thanks! """

        #sending to all eligible tenants
        tenant_numbers = [tenant['phone'] for tenant in eligible_tenants]
        results = telnyx_client.send_referral_blast(tenant_numbers, blast_message)
        
        #update tenant status to contacted
        for tenant in eligible_tenants:
            supabase_client.update_tenant_status(tenant['phone'], "contacted")
            supabase_client.add_tenant_message(tenant['phone'], blast_message, "ai")
            
            print(f"Blast sent to {len(eligible_tenants)} tenants")
            print(f"Results: {results}")
            
            return results
        
    except Exception as e:
        print(f"Error sending blast: {e}")
        return None
    
    
# For local testing
if __name__ == "__main__": 
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "blast":
        # Manual blast trigger
        print("Sending referral blast...")
        send_referral_blast()
        
    # Test with a fake tenant response
    test_event = {
        'body': json.dumps({
            'data': {
                'event_type': 'message.received',
                'payload': {
                    'from': {'phone_number': '+1555555555'},
                    'text': 'Yeah, I know someone! My friend Sarah is looking for a place. Her number is 111-555-1234'
                }
            }
        })
    }
    
    print("Testing referral assistant...")
    result = lambda_handler(test_event, None)
    print(f"Result: {result}")