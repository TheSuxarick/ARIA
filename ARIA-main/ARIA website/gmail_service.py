"""Gmail Integration Service for ARIA."""

import os
import base64
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from pathlib import Path


class GmailService:
    """Handle Gmail authentication and operations."""
    
    def __init__(self):
        self.credentials_file = Path(__file__).resolve().parent / 'credentials.json'
        self.token_file = Path(__file__).resolve().parent / 'token.json'
        self.scopes = [
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.modify'
        ]
        self.service = None
    
    def get_auth_url(self):
        """Get the authorization URL for Gmail OAuth."""
        if not self.credentials_file.exists():
            print(f"[Gmail] ❌ ERROR: Credentials file not found at {self.credentials_file}")
            return {"error": "Credentials file not found"}
        
        try:
            print(f"[Gmail] 🔑 Генерирую ссылку авторизации...")
            print(f"[Gmail] Credentials file: {self.credentials_file}")
            print(f"[Gmail] Scopes: {self.scopes}")
            
            flow = Flow.from_client_secrets_file(
                self.credentials_file,
                scopes=self.scopes,
                redirect_uri='http://localhost:5000/callback'
            )
            
            auth_url, state = flow.authorization_url(prompt='consent')
            print(f"[Gmail] ✅ Ссылка сгенерирована успешно")
            print(f"[Gmail] Auth URL: {auth_url[:80]}...")
            return {"auth_url": auth_url, "state": state}
        except Exception as e:
            print(f"[Gmail] ❌ Ошибка при генерации URL: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}
    
    def exchange_code_for_token(self, auth_code, state=None):
        """Exchange authorization code for access token."""
        if not self.credentials_file.exists():
            print(f"[Gmail] ERROR: Credentials file not found")
            return {"error": "Credentials file not found"}
        
        try:
            print(f"[Gmail] 🔄 Обмен кода на токен...")
            print(f"[Gmail] Code: {auth_code[:20]}...")
            
            flow = Flow.from_client_secrets_file(
                self.credentials_file,
                scopes=self.scopes,
                redirect_uri='http://localhost:5000/callback'
            )
            
            print(f"[Gmail] Запрос к Google для получения токена...")
            flow.fetch_token(code=auth_code)
            credentials = flow.credentials
            print(f"[Gmail] ✅ Токен получен успешно")
            
            # Save token for later use
            self._save_credentials(credentials)
            print(f"[Gmail] ✅ Токен сохранён в token.json")
            
            email = self._get_email_from_credentials(credentials)
            print(f"[Gmail] ✅ Email из профиля: {email}")
            
            return {
                "success": True,
                "email": email,
                "token": credentials.token,
                "refresh_token": credentials.refresh_token
            }
        except Exception as e:
            print(f"[Gmail] ❌ Ошибка обмена кода: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}
    
    def _save_credentials(self, credentials):
        """Save credentials to file for later use."""
        token_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        with open(self.token_file, 'w') as f:
            json.dump(token_data, f)
    
    def _load_credentials(self):
        """Load saved credentials from file."""
        if not self.token_file.exists():
            return None
        
        try:
            with open(self.token_file, 'r') as f:
                token_data = json.load(f)
            
            credentials = Credentials(
                token=token_data.get('token'),
                refresh_token=token_data.get('refresh_token'),
                token_uri=token_data.get('token_uri'),
                client_id=token_data.get('client_id'),
                client_secret=token_data.get('client_secret'),
                scopes=token_data.get('scopes')
            )
            
            # Refresh if needed
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                self._save_credentials(credentials)
            
            return credentials
        except Exception as e:
            print(f"Error loading credentials: {e}")
            return None
    
    def get_service(self):
        """Get Gmail service instance."""
        if self.service is not None:
            return self.service
        
        credentials = self._load_credentials()
        if credentials is None:
            print("[Gmail] No valid credentials found")
            return None
        
        try:
            self.service = build('gmail', 'v1', credentials=credentials)
            print("[Gmail] Service initialized successfully")
            return self.service
        except Exception as e:
            print(f"[Gmail] Error building service: {e}")
            return None
    
    def get_emails(self, max_results=10):
        """Fetch emails from Gmail inbox."""
        service = self.get_service()
        if service is None:
            return {"error": "Not authenticated with Gmail"}
        
        try:
            results = service.users().messages().list(
                userId='me',
                maxResults=max_results,
                q='in:inbox'
            ).execute()
            
            messages = results.get('messages', [])
            emails = []
            
            for message in messages:
                email_data = self._get_message_details(service, message['id'])
                if email_data:
                    emails.append(email_data)
            
            print(f"[Gmail] Fetched {len(emails)} emails from inbox")
            return {"emails": emails}
        except RefreshError as e:
            # Token expired and couldn't refresh
            print(f"[Gmail] Token refresh failed: {e}")
            self._clear_credentials()
            return {"error": "Authentication expired. Please log in again."}
        except Exception as e:
            print(f"[Gmail] Error fetching emails: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}
    
    def _get_message_details(self, service, message_id):
        """Get details of a specific email message."""
        try:
            message = service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            headers = message['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            from_addr = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            # Get body
            body = ''
            if 'parts' in message['payload']:
                for part in message['payload']['parts']:
                    if part['mimeType'] == 'text/plain':
                        data = part.get('body', {}).get('data', '')
                        if data:
                            body = base64.urlsafe_b64decode(data).decode('utf-8')
                            break
            else:
                data = message['payload'].get('body', {}).get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
            
            return {
                'id': message_id,
                'subject': subject,
                'from': from_addr,
                'date': date,
                'body': body[:200] + '...' if len(body) > 200 else body
            }
        except Exception as e:
            print(f"Error getting message details: {e}")
            return None
    
    def send_email(self, to, subject, body):
        """Send an email through Gmail."""
        service = self.get_service()
        if service is None:
            return {"error": "Not authenticated with Gmail"}
        
        try:
            message = self._create_message('me', to, subject, body)
            
            send_message = service.users().messages().send(
                userId='me',
                body=message
            ).execute()
            
            return {
                "success": True,
                "message_id": send_message['id']
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _create_message(self, sender, to, subject, message_text):
        """Create a message for sending."""
        from email.mime.text import MIMEText
        
        credentials = self._load_credentials()
        user_email = self._get_email_from_credentials(credentials)
        
        message = MIMEText(message_text)
        message['to'] = to
        message['from'] = user_email
        message['subject'] = subject
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {'raw': raw}
    
    def _get_email_from_credentials(self, credentials):
        """Get email address from credentials."""
        try:
            service = build('gmail', 'v1', credentials=credentials)
            profile = service.users().getProfile(userId='me').execute()
            return profile.get('emailAddress', 'unknown@gmail.com')
        except:
            return 'unknown@gmail.com'
    
    def _clear_credentials(self):
        """Clear saved credentials."""
        if self.token_file.exists():
            self.token_file.unlink()
        self.service = None
    
    def is_authenticated(self):
        """Check if user is authenticated with Gmail."""
        return self._load_credentials() is not None
