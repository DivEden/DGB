# pages/resizer.py
import io
import os
import re
import zipfile
import shutil
from typing import Dict, List, Optional, Tuple
from PIL import Image
from flask import Blueprint, render_template, request, send_file, jsonify
import base64

resizer_bp = Blueprint("resizer", __name__)

# Simpel in-memory lager for billeder (brug Redis i produktion)
_IMAGE_STORE: Dict[str, bytes] = {}
_GROUP_STORE: Dict[str, Dict] = {}

# Museum folder structure configuration
MUSEUM_BASE_PATH = r"\\dgb-file01\Museum\Museumsfaglig afdeling\0 Museets Samlinger\6 Genstandsfotos"

# For development/testing purposes, you can override the path
if os.environ.get('DGB_DEV_MODE'):
    MUSEUM_BASE_PATH = os.path.join(os.getcwd(), 'test_museum_folders')

def extract_case_number(filename: str) -> Optional[str]:
    """Extract case number from filename like 'AAB 0217x0054 a.jpg' or '0217x0054 a.jpg'"""
    # Look for pattern like 0217x0054 where 0217 is the case number
    match = re.search(r'(\d{4})x\d{4}', filename)
    if match:
        return match.group(1)
    return None

def get_case_folder_path(case_number: str) -> str:
    """Generate the full folder path for a case number"""
    if not case_number or len(case_number) != 4:
        raise ValueError(f"Invalid case number: {case_number}")
    
    case_num = int(case_number)
    
    # Determine the hundred range folder
    hundred_start = (case_num // 100) * 100
    if hundred_start == 0:
        hundred_folder = "Sag 0001-0099"
    else:
        hundred_end = hundred_start + 99
        hundred_folder = f"Sag {hundred_start:04d}-{hundred_end:04d}"
    
    # Determine the ten range folder
    ten_start = (case_num // 10) * 10
    ten_end = ten_start + 9
    ten_folder = f"Sag {ten_start:04d}-{ten_end:04d}"
    
    # Final case folder
    case_folder = case_number
    
    # Build full path
    full_path = os.path.join(
        MUSEUM_BASE_PATH,
        hundred_folder,
        ten_folder,
        case_folder
    )
    
    return full_path

def organize_files_to_museum_folders(processed_files: List[Dict]) -> Dict:
    """Organize processed files to their correct museum folders and return results"""
    organization_results = {
        'success': [],
        'errors': [],
        'folders_created': set()
    }
    
    for file_pair in processed_files:
        try:
            # Extract case number from filename
            filename = file_pair['large']['filename']
            case_number = extract_case_number(filename)
            
            if not case_number:
                organization_results['errors'].append(f"Could not extract case number from {filename}")
                continue
            
            # Get target folder path
            target_folder = get_case_folder_path(case_number)
            
            # Create folder structure if it doesn't exist
            try:
                os.makedirs(target_folder, exist_ok=True)
                organization_results['folders_created'].add(target_folder)
            except OSError as e:
                organization_results['errors'].append(f"Failed to create folder {target_folder}: {str(e)}")
                continue
            
            # Only move large versions to museum folders (directly, no subfolder)
            token = file_pair['large']['token']
            filename = file_pair['large']['filename']
            
            # Get image data (but don't pop it yet, we need it for download too)
            image_data = _IMAGE_STORE.get(token)
            if not image_data:
                organization_results['errors'].append(f"No image data found for {filename}")
                continue
            
            # Write file directly to case folder (no size subfolder)
            target_file_path = os.path.join(target_folder, filename)
            
            try:
                with open(target_file_path, 'wb') as f:
                    f.write(image_data)
                organization_results['success'].append(f"Saved {filename} to {target_file_path}")
            except OSError as e:
                organization_results['errors'].append(f"Failed to save {filename}: {str(e)}")
            
        except Exception as e:
            organization_results['errors'].append(f"Error processing {filename}: {str(e)}")
    
    return organization_results

def _store_image(data: bytes) -> str:
    import secrets
    token = secrets.token_urlsafe(24)
    _IMAGE_STORE[token] = data
    return token

def _store_group_data(group_data: Dict) -> str:
    import secrets
    token = secrets.token_urlsafe(24)
    _GROUP_STORE[token] = group_data
    return token

def _pop_image(token: str) -> Optional[bytes]:
    return _IMAGE_STORE.pop(token, None)

def _get_group_data(token: str) -> Optional[Dict]:
    return _GROUP_STORE.get(token, None)

def create_thumbnail(image_data: bytes, max_size_kb: int = 300) -> bytes:
    """Create a compressed thumbnail with size limit in KB - aims for target size"""
    image = Image.open(io.BytesIO(image_data))
    
    # konverter til RGB (for PNG with transparency, etc.)
    if image.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Klap hesten med resize - først prøves der at ramme KB mål
    temp_image = image.copy()
    quality = 95
    
    for attempt in range(12):
        output = io.BytesIO()
        temp_image.save(output, format='JPEG', quality=quality, optimize=True)
        size_kb = len(output.getvalue()) / 1024
        
        # Hvis inden 15% - accepter det
        if size_kb <= max_size_kb and size_kb >= max_size_kb * 0.75:
            output.seek(0)
            return output.getvalue()
        elif size_kb <= max_size_kb:
            # prøv højere kvalitet hvis muligt
            if quality < 95:
                quality = min(95, quality + 5)
            else:
                # allerede maks? accepter resultat
                output.seek(0)
                return output.getvalue()
        else:
            # gør kvalitet lavere mere gradvist
            if quality > 70:
                quality -= 5
            else:
                quality -= 10
        
        # hvis kvalitet er meget lav, resize billede og reset kvalitet
        if quality <= 40 and max(temp_image.size) > 600:
            ratio = 0.85
            new_size = (int(temp_image.width * ratio), int(temp_image.height * ratio))
            temp_image = image.resize(new_size, Image.Resampling.LANCZOS)
            quality = 85
            image = temp_image  # Update
    
    # Det endelige save - lav hele det område her om, både over og under
    output = io.BytesIO()
    temp_image.save(output, format='JPEG', quality=quality, optimize=True)
    output.seek(0)
    return output.getvalue()

def resize_image(image_data: bytes, max_size: int = None) -> bytes:
    """ONLY rename/format convert - NO resizing or quality loss for large images"""
    # STORE BILLEDER SKAL IKKE PILLES VED (:
    image = Image.open(io.BytesIO(image_data))
    
    # rgb konvertering (for PNG with transparency, etc.)
    if image.format == 'JPEG' and image.mode == 'RGB':
        # allerede formateret? perfekt, returner original data uændret
        return image_data
    
    
    if image.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    
    # gem med absolut maksimum kvalitet og ingen optimering
    output = io.BytesIO()
    image.save(output, format='JPEG', quality=100, optimize=False)
    output.seek(0)
    return output.getvalue()

def get_image_info(image_data: bytes) -> Dict:
    """Get basic info about an image"""
    image = Image.open(io.BytesIO(image_data))
    return {
        'width': image.width,
        'height': image.height,
        'format': image.format,
        'mode': image.mode,
        'size_bytes': len(image_data)
    }

@resizer_bp.route("/", methods=["GET", "POST"])
def view():
    if request.method == "GET":
        return render_template('resizer.html', current_page='resizer')
    
    # ærlig talt pas
    return handle_form_submission()

def handle_form_submission():
    """Handle form submission for processing groups"""
    try:
        # hent uploadede filer
        files = request.files.getlist('images')
        if not files:
            return render_template('resizer.html', 
                                 current_page='resizer',
                                 error='Ingen billeder uploadet')
        
        # hent grupper data
        groups_data = request.form.get('groups_data')
        if not groups_data:
            return render_template('resizer.html', 
                                 current_page='resizer',
                                 error='Ingen grupper at behandle')
        
        import json
        groups = json.loads(groups_data)
        
        # hent settings (only small image settings needed)
        small_max_size_kb = int(request.form.get('small_max_size', 300))  # KB now
        use_aab_prefix = request.form.get('use_aab_prefix') == 'on'
        auto_organize = request.form.get('auto_organize') == 'on'
        
        # gem lidt data osv
        uploaded_files = []
        for file in files:
            if file and file.filename:
                image_data = file.read()
                uploaded_files.append(image_data)
        
        
        processed_files = []
        
        for group in groups:
            group_name = group.get('name', 'unnamed')
            image_indices = group.get('images', [])
            
            # Filnavne: AAB <gruppenavn> a.jpg, AAB <gruppenavn> b.jpg, ... eller uden AAB
            letters = [chr(97 + i) for i in range(len(image_indices))]  # a, b, c, ...
            
            for i, (image_index, letter) in enumerate(zip(image_indices, letters)):
                if image_index < len(uploaded_files):
                    image_data = uploaded_files[image_index]
                    
                    # Filnavne (same for both versions)
                    filename = f"AAB {group_name} {letter}.jpg" if use_aab_prefix else f"{group_name} {letter}.jpg"
                    
                    # Små versioner (komprimeret efter KB)
                    small_image = create_thumbnail(image_data, small_max_size_kb)
                    small_token = _store_image(small_image)
                    
                    # Store version (original kvalitet, ingen resize)
                    large_image = resize_image(image_data)  # No max_size parameter
                    large_token = _store_image(large_image)
                    
                    processed_files.append({
                        'small': {'token': small_token, 'filename': filename},
                        'large': {'token': large_token, 'filename': filename}
                    })
        
        # Auto-organize files if requested
        organization_results = None
        if auto_organize:
            organization_results = organize_files_to_museum_folders(processed_files)
        
        # Always create download option (gem gruppe data til download)
        group_token = _store_group_data({
            'files': processed_files,
            'settings': {
                'small_max_size_kb': small_max_size_kb,
                'use_aab_prefix': use_aab_prefix
            }
        })
        
        # Always show normal results page with download option
        # If auto_organize was used, include the organization results for display
        return render_template('resizer.html',
                             current_page='resizer',
                             step='results',
                             processed_count=len(processed_files),
                             group_token=group_token,
                             organization_results=organization_results,
                             auto_organized=auto_organize and organization_results and organization_results.get('success'))
                             
    except Exception as e:
        return render_template('resizer.html',
                             current_page='resizer',
                             error=f'Fejl ved behandling: {str(e)}')

@resizer_bp.route("/download_zip")
def download_zip():
    """Create and download ZIP file with all processed images"""
    try:
        token = request.args.get('token')
        if not token:
            return "Mangler token", 400
        
        group_data = _get_group_data(token)
        if not group_data:
            return "Token udløbet eller ugyldigt", 410
        
        # Zip it up
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            
            for file_pair in group_data['files']:
                # Tilføj de små
                small_data = _pop_image(file_pair['small']['token'])
                if small_data:
                    zip_file.writestr(f"small/{file_pair['small']['filename']}", small_data)
                
                # Også de store
                large_data = _pop_image(file_pair['large']['token'])
                if large_data:
                    zip_file.writestr(f"large/{file_pair['large']['filename']}", large_data)
        
        zip_buffer.seek(0)
        
        return send_file(
            io.BytesIO(zip_buffer.getvalue()),
            mimetype='application/zip',
            as_attachment=True,
            download_name='processed_images.zip'
        )
        
    except Exception as e:
        return f"Fejl ved download: {str(e)}", 500
