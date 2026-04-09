"""Gmail Integration Service for ARIA."""

import os
import base64
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime as _email_parsedate
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from pathlib import Path


def _safe_parse_date(date_str: str) -> datetime:
    """Parse RFC 2822 Date header → UTC naive datetime."""
    if not date_str:
        return datetime.utcnow()
    try:
        dt = _email_parsedate(date_str.strip())
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        for fmt in ('%a, %d %b %Y %H:%M:%S', '%d %b %Y %H:%M:%S'):
            try:
                clean = re.sub(r'\s+[+-]\d{4}.*$', '', date_str.strip())
                clean = re.sub(r'\s+\([A-Z]+\)$', '', clean).strip()
                return datetime.strptime(clean, fmt)
            except Exception:
                continue
        return datetime.utcnow()


def _extract_body(payload: dict) -> str:
    """Recursively extract best body (prefer text/html, fallback text/plain)."""
    mime = payload.get('mimeType', '')
    parts = payload.get('parts', [])

    if parts:
        html_body = plain_body = ''
        for part in parts:
            result = _extract_body(part)
            part_mime = part.get('mimeType', '')
            if 'html' in part_mime and not html_body:
                html_body = result
            elif 'plain' in part_mime and not plain_body:
                plain_body = result
            elif result and not html_body and not plain_body:
                html_body = result
        return html_body or plain_body

    data = payload.get('body', {}).get('data', '')
    if data:
        try:
            return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
        except Exception:
            pass
    return payload.get('snippet', '')


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
        self._service_by_email = {}

    def _load_client_id_secret(self):
        cfg = self._load_client_config()
        # credentials.json can be "installed" or "web"
        block = cfg.get('installed') or cfg.get('web') or {}
        return (block.get('client_id', ''), block.get('client_secret', ''))

    def _load_credentials_from_db(self, email: str):
        """Build google.oauth2.credentials.Credentials for a specific GmailAccount from DB."""
        if not email:
            return None
        try:
            from models import GmailAccount, db  # local import to avoid circular deps
            acct = GmailAccount.query.filter_by(email=email).first()
            if not acct or not acct.access_token:
                return None

            client_id, client_secret = self._load_client_id_secret()
            if not client_id or not client_secret:
                return None

            creds = Credentials(
                token=acct.access_token,
                refresh_token=acct.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=client_id,
                client_secret=client_secret,
                scopes=self.scopes
            )

            # Attempt refresh (will no-op if not expired / no refresh token)
            try:
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    acct.access_token = creds.token or acct.access_token
                    db.session.add(acct)
                    db.session.commit()
            except Exception:
                # If refresh fails, leave as-is; callers will handle auth errors.
                pass

            return creds
        except Exception:
            return None
    
    def _load_client_config(self):
        """Read and parse credentials.json with explicit UTF-8 encoding."""
        if not self.credentials_file.exists():
            raise FileNotFoundError(f"credentials.json not found at {self.credentials_file}")
        with open(str(self.credentials_file), 'r', encoding='utf-8') as f:
            raw = f.read().strip()
        if not raw:
            raise ValueError("credentials.json is empty")
        return json.loads(raw)

    def get_auth_url(self):
        """Get the authorization URL for Gmail OAuth."""
        try:
            print(f"[Gmail] 🔑 Генерирую ссылку авторизации...")
            client_config = self._load_client_config()
            flow = Flow.from_client_config(
                client_config,
                scopes=self.scopes,
                redirect_uri='http://localhost:5000/api/gmail/callback'
            )
            auth_url, state = flow.authorization_url(prompt='consent', access_type='offline')
            print(f"[Gmail] ✅ Auth URL сгенерирован")
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
            
            client_config = self._load_client_config()
            flow = Flow.from_client_config(
                client_config,
                scopes=self.scopes,
                redirect_uri='http://localhost:5000/api/gmail/callback'
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
            'scopes': list(credentials.scopes) if credentials.scopes else []
        }
        
        with open(str(self.token_file), 'w') as f:
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
    
    def get_service(self, email: str = None):
        """Get Gmail service instance (optionally for a specific GmailAccount email)."""
        if email:
            if email in self._service_by_email and self._service_by_email[email] is not None:
                return self._service_by_email[email]
            credentials = self._load_credentials_from_db(email)
            if credentials is None:
                return None
            try:
                svc = build('gmail', 'v1', credentials=credentials)
                self._service_by_email[email] = svc
                return svc
            except Exception as e:
                print(f"[Gmail] Error building service for {email}: {e}")
                self._service_by_email[email] = None
                return None

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
    
    def get_emails(self, max_results=10, email: str = None):
        """Fetch emails from Gmail inbox."""
        service = self.get_service(email=email)
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
    
    def _get_message_metadata(self, service, message_id):
        """Fetch only headers + labels — no body download (very fast)."""
        try:
            message = service.users().messages().get(
                userId='me', id=message_id, format='metadata',
                metadataHeaders=['Subject', 'From', 'To', 'Date']
            ).execute()

            headers = {h['name'].lower(): h['value']
                       for h in message['payload'].get('headers', [])}

            date_str = headers.get('date', '')
            return {
                'id':       message_id,
                'subject':  headers.get('subject', '(No Subject)'),
                'from':     headers.get('from', 'Unknown'),
                'to':       headers.get('to', ''),
                'date':     date_str,
                'date_dt':  _safe_parse_date(date_str),
                'snippet':  message.get('snippet', ''),
                'body':     '',          # fetched on demand
                'is_read':  'UNREAD' not in message.get('labelIds', []),
            }
        except Exception as e:
            print(f"[Gmail] Error getting metadata {message_id}: {e}")
            return None

    def _batch_get_metadata(self, service, message_ids: list) -> list:
        """Fetch metadata for many emails using Gmail batch HTTP requests.

        Sends up to 100 API calls per HTTP request — ~50× faster than one-by-one.
        """
        results = {}

        def _cb(request_id, response, exception):
            if exception:
                print(f"[Gmail] Batch metadata error {request_id}: {exception}")
                return
            if not response:
                return
            headers = {h['name'].lower(): h['value']
                       for h in response.get('payload', {}).get('headers', [])}
            date_str = headers.get('date', '')
            results[request_id] = {
                'id':       request_id,
                'subject':  headers.get('subject', '(No Subject)'),
                'from':     headers.get('from', 'Unknown'),
                'to':       headers.get('to', ''),
                'date':     date_str,
                'date_dt':  _safe_parse_date(date_str),
                'snippet':  response.get('snippet', ''),
                'body':     '',
                'is_read':  'UNREAD' not in response.get('labelIds', []),
            }

        BATCH_SIZE = 100
        for i in range(0, len(message_ids), BATCH_SIZE):
            chunk = message_ids[i:i + BATCH_SIZE]
            batch = service.new_batch_http_request(callback=_cb)
            for mid in chunk:
                batch.add(
                    service.users().messages().get(
                        userId='me', id=mid, format='metadata',
                        metadataHeaders=['Subject', 'From', 'To', 'Date']
                    ),
                    request_id=mid,
                )
            try:
                batch.execute()
            except Exception as e:
                print(f"[Gmail] Batch execute error (chunk {i}): {e}")

        # Preserve original ordering
        ordered = []
        for mid in message_ids:
            if mid in results:
                ordered.append(results[mid])
        return ordered

    def _get_message_details(self, service, message_id):
        """Fetch full message including body (used for on-demand body loading)."""
        try:
            message = service.users().messages().get(
                userId='me', id=message_id, format='full'
            ).execute()

            headers = {h['name'].lower(): h['value']
                       for h in message['payload'].get('headers', [])}

            date_str = headers.get('date', '')
            body = _extract_body(message['payload']) or message.get('snippet', '')

            return {
                'id':       message_id,
                'subject':  headers.get('subject', '(No Subject)'),
                'from':     headers.get('from', 'Unknown'),
                'to':       headers.get('to', ''),
                'date':     date_str,
                'date_dt':  _safe_parse_date(date_str),
                'body':     body,
                'is_read':  'UNREAD' not in message.get('labelIds', []),
            }
        except Exception as e:
            print(f"[Gmail] Error getting message {message_id}: {e}")
            return None

    def get_emails_for_sync(self, query: str = 'in:inbox newer_than:2m',
                             max_results: int = 500,
                             email: str = None):
        """Fetch email metadata for sync (fast — no body download).

        Returns dict with keys 'emails' (list) and 'message_ids' (set of gmail IDs).
        """
        service = self.get_service(email=email)
        if service is None:
            return {'error': 'Not authenticated with Gmail'}

        try:
            # Step 1: list all matching message IDs (paginated)
            list_params = {'userId': 'me', 'q': query}
            if max_results:
                list_params['maxResults'] = min(max_results, 500)

            page_token = None
            all_messages = []
            while True:
                if page_token:
                    list_params['pageToken'] = page_token
                result = service.users().messages().list(**list_params).execute()
                all_messages.extend(result.get('messages', []))
                page_token = result.get('nextPageToken')
                if not page_token or (max_results and len(all_messages) >= max_results):
                    break

            message_ids = {m['id'] for m in all_messages}

            # Step 2: batch-fetch metadata (100 calls per HTTP request, ~50× faster)
            ordered_ids = [m['id'] for m in all_messages]
            emails = self._batch_get_metadata(service, ordered_ids)

            print(f"[Gmail] Batch-fetched metadata for {len(emails)}/{len(ordered_ids)} emails")
            return {'emails': emails, 'message_ids': message_ids}
        except RefreshError:
            self._clear_credentials()
            return {'error': 'Authentication expired. Please log in again.'}
        except Exception as e:
            print(f'[Gmail] Sync error: {e}')
            return {'error': str(e)}
    
    def send_email(self, to, subject, body, email: str = None):
        """Send an email through Gmail."""
        service = self.get_service(email=email)
        if service is None:
            return {"error": "Not authenticated with Gmail"}
        
        try:
            message = self._create_message('me', to, subject, body, from_email=email)
            
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
    
    def _create_message(self, sender, to, subject, message_text, from_email: str = None):
        """Create a message for sending."""
        from email.mime.text import MIMEText

        user_email = from_email
        if not user_email:
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
        self._service_by_email = {}
    
    def is_authenticated(self, email: str = None):
        """Check if user is authenticated with Gmail (optionally for a specific GmailAccount email)."""
        if email:
            try:
                from models import GmailAccount
                acct = GmailAccount.query.filter_by(email=email).first()
                return bool(acct and acct.access_token)
            except Exception:
                return False
        return self._load_credentials() is not None
