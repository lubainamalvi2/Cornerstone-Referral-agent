import os
from dotenv import load_dotenv
from pathlib import Path

current_dir = Path(__file__).parent  # utils/
src_dir = current_dir.parent         # src/
project_dir = src_dir.parent         # project root
env_file = project_dir / '.env'

load_dotenv(env_file)

from supabase import create_client, Client
from typing import Dict, Optional, List
from datetime import datetime

class SupabaseClient:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables")
        self.client: Client = create_client(url, key)
        
    # tenant methods
    def get_tenant_by_phone(self, phone: str) -> Optional[Dict]:
        """
        Get tenant by phone number
        """
        try:
            response = self.client.table("tenants").select("*").eq("phone", phone).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"Error getting tenant by phone: {e}")
            return None
        
    def create_tenant(self, phone: str, name: str = "", email: str = "") -> Optional[Dict]:
        """
        Create a new tenant record
        """
        try:
            tenant_data = {
                "phone": phone,
                "name": name,
                "email": email, 
                "status": "active",
                "last_contacted": None,
                "referrals_provided": 0,
                "conversation_history": ""
            }
            response = self.client.table("tenants").insert(tenant_data).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"Error creating tenant: {e}")
            return None
        
    def update_tenant_status(self, phone: str, status: str) -> bool:
        """
        Update tenant status (active, contacted, declined, completed)
        """
        try:
            updates = {
                "status": status,
                "last_contacted": datetime.now().isoformat()
            }
            response = self.client.table("tenants").update(updates).eq("phone", phone).execute()
            return bool(response.data)
        except Exception as e:
            print(f"Error updating tenant status: {e}")
            return False
        
    def add_tenant_message(self, phone: str, message: str, sender: str = "tenant"):
        """
        Add a message to tenants conversation history
        """
        try: 
            tenant = self.get_tenant_by_phone(phone)
            if tenant:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                existing_history = tenant.get("conversation_history", "")
                sender_label = "Tenant" if sender == "tenant" else "AI"
                new_entry = f"{timestamp} - {sender_label}: {message}\n"
                
                updated_history = existing_history + new_entry
                
                updates = {
                    "conversation_history": updated_history,
                    "last_contacted": datetime.now().isoformat()
                }
                self.client.table("tenants").update(updates).eq("phone", phone).execute()
        except Exception as e:
            print(f"Error adding tenant message: {e}")
            
    def get_active_tenants(self) -> List[Dict]:
        """
        Get all active tenants for referral blasts
        """
        try:
            response = self.client.table("tenants").select("*").eq("status", "active").execute()
            return response.data or []
        except Exception as e:
            print(f"Error getting active tenants: {e}")
            return []
    
    def get_tenants_for_blast(self, days_since_last_contact: int = 30) -> List[Dict]:
        """
        Get tenants eligible for referral blast (haven't been contacted recently)
        """
        try:
            # get tenants who haven't been contacted in X days or never contacted
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days= days_since_last_contact)
            
            response = self.client.table("tenants").select("*").eq("status", "active").or_(f"last_contacted.is.null,last_contacted.lt.{cutoff_date.isoformat()}"
                                                                                            ).execute()
            return response.data or []
        except Exception as e:
            print(f"Error getting tenants for blast: {e}")
            return []
    
    def increment_tenant_referrals(self, phone: str) -> bool:
        """
        Increment the referral count for a tenant
        """
        try:
            tenant = self.get_tenant_by_phone(phone)
            if tenant:
                current_count = tenant.get("referrals_provided", 0)
                updates = {
                    "referrals_provided": current_count + 1,
                    "last_contacted": datetime.now().isoformat()
                }
                result = self.client.table("tenants").update(updates).eq("phone", phone).execute()
                return bool(result.data)
            return False
        except Exception as e:
            print(f"Error incrementing tenant referrals: {e}")
            return False
        
    # lead methods
    
    def get_lead_by_phone(self, phone: str) -> Optional[Dict]:
        """
        Get lead record by phone number
        """
        try:
            response = self.client.table("leads").select("*").eq("phone", phone).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"Error getting lead by phone: {e}")
            return None
        
    def create_referral_lead(self, referral_info: Dict, referring_tenant_phone: str) -> Optional[Dict]:
        """
        Create a new lead from referral information
        """
        try:
            #check if lead already exists
            existing_lead = self.get_lead_by_phone(referral_info.get('phone', ''))
                
            if existing_lead:
                #update the existing elad with referral source if not already set
                if not existing_lead.get('referral_source'):
                    updates = {
                        'referral_source': f"Referred By {referring_tenant_phone}",
                        'name': referral_info.get('name', existing_lead.get('name', ''))
                    }
                    self.client.table("leads").update(updates).eq("phone", referral_info['phone']).execute()
                return existing_lead
            
            # create new lead with referral information
            lead_data = {
                "phone": referral_info.get('phone', ''),
                "name": referral_info.get('name', ''),
                "email": referral_info.get('email', ''),
                "beds": "", 
                "baths": "",
                "move_in_date": "", 
                "price": "",
                "location": "",
                "amenities": "",
                "tour_availability": "",
                "tour_ready": False,
                "chat_history": f"Referral from {referring_tenant_phone}\n", 
                "referral_source": f"Referred by {referring_tenant_phone}"
            }
            
            response = self.client.table("leads").insert(lead_data).execute()
            
            if response.data:
                #increment referring tenant's referral count
                self.increment_tenant_referrals(referring_tenant_phone)
                return response.data[0]
            return None
        except Exception as e:
            print(f"Error creating referral lead: {e}")
            return None
    
    def create_lead(self, phone: str, initial_message: str = "") -> Optional[Dict]:
        """
        Create a new lead record (for compatibility with agent 1)
        """
        
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            initial_chat = f"{timestamp} - Lead: {initial_message}\n" if initial_message else ""
            
            lead_data = {
                "phone": phone,
                "name": "",
                "email": "",
                "beds": "",
                "baths": "",
                "move_in_date": "",
                "price": "",
                "location": "",
                "amenities": "",
                "tour_availability": "",
                "tour_ready": False,
                "chat_history": initial_chat,
                "referral_source": ""
            }
            response = self.client.table("leads").insert(lead_data).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"Error creating lead: {e}")
            return None
    
    # bulk operations
    def bulk_create_tenants(self, tenant_list: List[Dict]) -> bool:
        """
        Bulk create tenant records from a list
        """
        try:
            tenant_data = []
            for tenant in tenant_list:
                tenant_data.append({
                    "phone": tenant.get('phone', ''),
                    "name": tenant.get('name', ''),
                    "email": tenant.get('email', ''),
                    "status": "active", 
                    "last_contacted": None,
                    "referrals_provided": 0,
                    "conversation_history": ""
                })
                
            response = self.client.table("tenants").insert(tenant_data).execute()
            return bool(response.data)
        except Exception as e:
            print(f"Error bulk creating tenants: {e}")
            return False
    
    # reporting
    def get_referral_stats(self) -> Dict:
        """
        Get statistics about referral program
        """
        try:
            # get tenant stats
            total_tenants = self.client.table("tenants").select("*", count ="exact").execute()
            contacted_tenants = self.client.table("tenants").select("*", count ="exact").neq("last_contacted", None).execute()
            
            # get referral stats
            total_referrals = self.client.table("leads").select("*", count ="exact").neq("referral_source", "").execute()
            
            # get top referring tenants
            top_referrers = self.client.table("tenants").select("*").gt("referrals_provided", 0).order("referrals_provided", desc = True).limit(5).execute()
            
            return {
                "total_tenants": total_tenants.count,
                "contacted_tenants": contacted_tenants.count,
                "total_referrals": total_referrals.count,
                "top_referrers": top_referrers.data
            }
        except Exception as e:
            print(f"Error getting referral stats: {e}")
            return {}
                            