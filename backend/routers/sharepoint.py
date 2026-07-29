import os
import urllib.parse
import msal
import requests
import uuid
import base64

def get_graph_token():
    client_id = os.getenv("AZURE_CLIENT_ID")
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    
    if not client_id or not tenant_id or not client_secret:
        raise ValueError("Missing Azure credentials in .env")

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id, authority=authority, client_credential=client_secret
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" in result:
        return result["access_token"]
    raise ValueError(f"Failed to acquire token: {result.get('error_description')}")

def encode_sharing_url(url):
    encoded = base64.b64encode(url.encode("utf-8")).decode("utf-8")
    return "u!" + encoded.rstrip("=").replace("+", "-").replace("/", "_")

def resolve_share_url(token, url):
    encoded_url = encode_sharing_url(url)
    headers = {'Authorization': f'Bearer {token}'}
    res = requests.get(f"https://graph.microsoft.com/v1.0/shares/{encoded_url}/driveItem", headers=headers)
    if res.status_code == 200:
        data = res.json()
        return data['parentReference']['driveId'], data['id']
    return None, None

def parse_sharepoint_url(url: str):
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.netloc
    
    query = dict(urllib.parse.parse_qsl(parsed.query))
    if 'id' in query:
        folder_path_full = query['id']
        path_parts = [p for p in folder_path_full.split('/') if p]
    else:
        path_parts = [p for p in parsed.path.split('/') if p]
    
    if len(path_parts) >= 2 and path_parts[0] in ['personal', 'sites', 'teams']:
        site_path = f"/{path_parts[0]}/{path_parts[1]}"
        if len(path_parts) > 2 and path_parts[2].lower() == 'documents':
            folder_path = "/".join(path_parts[3:])
        else:
            folder_path = "/".join(path_parts[2:])
    else:
        site_path = "/"
        folder_path = "/".join(path_parts)
        
    if folder_path.endswith("AllItems.aspx"):
        folder_path = folder_path.replace("Forms/AllItems.aspx", "").strip("/")
        
    return hostname, site_path, urllib.parse.unquote(folder_path)

def get_site_id(token, hostname, site_path):
    headers = {'Authorization': f'Bearer {token}'}
    if site_path == "/":
        url = f"https://graph.microsoft.com/v1.0/sites/{hostname}"
    else:
        url = f"https://graph.microsoft.com/v1.0/sites/{hostname}:{site_path}"
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        raise ValueError(f"Could not find SharePoint site. Make sure the URL is correct and the App has Sites.ReadWrite.All permission. Details: {res.text}")
    return res.json().get('id')

def get_default_drive_id(token, site_id):
    headers = {'Authorization': f'Bearer {token}'}
    res = requests.get(f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive", headers=headers)
    if res.status_code == 200:
        return res.json().get('id')
    res = requests.get(f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives", headers=headers)
    data = res.json()
    if 'value' in data and len(data['value']) > 0:
        return data['value'][0]['id']
    raise ValueError("No document library found in the SharePoint site.")

def upload_file_to_drive(token, drive_id, folder_path, filename, file_path, base_item_id=None):
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/octet-stream'}
    if folder_path and folder_path.lower().startswith("shared documents"):
        folder_path = folder_path[len("shared documents"):].strip("/")
    
    if base_item_id:
        if folder_path:
            upload_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{base_item_id}:/{folder_path}/{filename}:/content"
        else:
            upload_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{base_item_id}:/{filename}:/content"
    else:
        if folder_path:
            upload_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{folder_path}/{filename}:/content"
        else:
            upload_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{filename}:/content"
        
    with open(file_path, 'rb') as f:
        res = requests.put(upload_url, headers=headers, data=f)
    if res.status_code not in [200, 201]:
        raise ValueError(f"Failed to upload {filename}. Details: {res.text}")
    return res.json().get('webUrl')

def create_folder_in_drive(token, drive_id, parent_path, folder_name, base_item_id=None):
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        "name": folder_name,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "fail" 
    }
    if base_item_id:
        if parent_path:
            url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{base_item_id}:/{parent_path}:/children"
        else:
            url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{base_item_id}/children"
    else:
        if parent_path:
            url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{parent_path}:/children"
        else:
            url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"
            
    requests.post(url, headers=headers, json=payload)

def export_workspace_to_sharepoint(target_url: str, package_data: dict, package_name: str, db):
    token = get_graph_token()
    
    # Try resolving via Shares API
    drive_id, base_item_id = resolve_share_url(token, target_url)
    base_folder_path = ""
    
    if not drive_id:
        hostname, site_path, base_folder_path = parse_sharepoint_url(target_url)
        site_id = get_site_id(token, hostname, site_path)
        drive_id = get_default_drive_id(token, site_id)
    
    folder_map = {f['id']: f for f in package_data.get('folders', [])}
    
    def get_relative_folder_path(folder_id):
        if folder_id not in folder_map:
            return ""
        f = folder_map[folder_id]
        if f.get('parentId'):
            parent_path = get_relative_folder_path(f['parentId'])
            return f"{parent_path}/{f['name']}".strip("/")
        return f['name'].strip("/")

    def get_full_folder_path(folder_id):
        rel_path = get_relative_folder_path(folder_id)
        pkg_folder = package_name.strip("/")
        combined = f"{pkg_folder}/{rel_path}" if rel_path else pkg_folder
        
        if base_item_id:
            return combined
        else:
            if not combined: return base_folder_path
            return f"{base_folder_path}/{combined}".strip("/")
            
    # 1. Create the root package folder
    pkg_folder = package_name.strip("/")
    create_folder_in_drive(token, drive_id, base_folder_path if not base_item_id else "", pkg_folder, base_item_id)
    
    # 2. Sort folders by depth and create them so empty folders are preserved
    folders_with_depth = []
    for f in package_data.get('folders', []):
        rel = get_relative_folder_path(f['id'])
        depth = rel.count('/')
        folders_with_depth.append((depth, f, rel))
        
    folders_with_depth.sort(key=lambda x: x[0])
    
    for depth, f, rel in folders_with_depth:
        if not rel: continue
        parts = rel.split('/')
        folder_name = parts[-1]
        parent_rel = "/".join(parts[:-1])
        
        if parent_rel:
            parent_path = f"{pkg_folder}/{parent_rel}"
        else:
            parent_path = pkg_folder
            
        if not base_item_id and base_folder_path:
            parent_path = f"{base_folder_path}/{parent_path}".strip("/")
            
        create_folder_in_drive(token, drive_id, parent_path, folder_name, base_item_id)
            
    from models.database import ProjectFile
    
    for item in package_data.get('items', []):
        file_info = item.get('file', {})
        if not file_info.get('id'):
            continue
            
        pf = db.query(ProjectFile).filter(ProjectFile.id == file_info['id']).first()
        if not pf or not pf.filename:
            continue
            
        full_folder_path = get_full_folder_path(item.get('folderId'))
        file_path = os.path.join("uploads/project_files", pf.filename)
        
        # Ensure filename retains extension
        upload_name = pf.name
        if "." not in upload_name and "." in pf.filename:
            upload_name += os.path.splitext(pf.filename)[1]
            
        if os.path.exists(file_path):
            upload_file_to_drive(token, drive_id, full_folder_path, upload_name, file_path, base_item_id)
            
    return target_url

def import_workspace_from_sharepoint(target_url: str, db):
    token = get_graph_token()
    
    # Try resolving via Shares API
    drive_id, base_item_id = resolve_share_url(token, target_url)
    base_folder_path = ""
    
    if not drive_id:
        hostname, site_path, base_folder_path = parse_sharepoint_url(target_url)
        site_id = get_site_id(token, hostname, site_path)
        drive_id = get_default_drive_id(token, site_id)
    
    headers = {'Authorization': f'Bearer {token}'}
    folders = []
    items = []
    
    from models.database import ProjectFile
    
    def process_folder(graph_folder_path, parent_frontend_id=None, current_item_id=None):
        if current_item_id:
            if graph_folder_path:
                list_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{current_item_id}:/{graph_folder_path}:/children"
            else:
                list_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{current_item_id}/children"
        else:
            if graph_folder_path:
                list_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{graph_folder_path}:/children"
            else:
                list_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"
            
        res = requests.get(list_url, headers=headers)
        if res.status_code != 200:
            raise ValueError(f"Could not read folder '{graph_folder_path}'. Details: {res.text}")
            
        children = res.json().get('value', [])
        
        for child in children:
            if 'folder' in child:
                new_folder_id = str(uuid.uuid4())
                folders.append({
                    "id": new_folder_id,
                    "name": child['name'],
                    "parentId": parent_frontend_id
                })
                # if we have base_item_id, graph_folder_path is relative
                new_graph_path = f"{graph_folder_path}/{child['name']}" if graph_folder_path else child['name']
                process_folder(new_graph_path, new_folder_id, base_item_id)
            elif 'file' in child:
                download_url = child.get('@microsoft.graph.downloadUrl')
                if download_url:
                    local_filename = f"{uuid.uuid4().hex}_{child['name']}"
                    local_path = os.path.join("uploads/project_files", local_filename)
                    
                    file_res = requests.get(download_url)
                    with open(local_path, 'wb') as f:
                        f.write(file_res.content)
                        
                    pf = ProjectFile(name=child['name'], filename=local_filename, category="Imported")
                    db.add(pf)
                    db.commit()
                    db.refresh(pf)
                    
                    items.append({
                        "id": str(uuid.uuid4()),
                        "folderId": parent_frontend_id,
                        "file": {
                            "id": pf.id,
                            "name": pf.name,
                            "category": pf.category
                        }
                    })
                    
    process_folder(base_folder_path, None, base_item_id)
    
    return {
        "folders": folders,
        "items": items
    }
