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

def get_case_folder_relative(case_number: str) -> str:
    """Generate relative folder path for ZIP structure (without base path)"""
    if not case_number or len(case_number) != 4:
        return "unknown"
    
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
    
    # Build relative path for ZIP
    return f"Museum/{hundred_folder}/{ten_folder}/{case_number}"

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
            case_folder = get_case_folder_path(case_number)
            
            # Create "museumsklar" subfolder inside case folder
            target_folder = os.path.join(case_folder, "museumsklar")
            
            # Create folder structure if it doesn't exist
            try:
                os.makedirs(target_folder, exist_ok=True)
                organization_results['folders_created'].add(target_folder)
            except OSError as e:
                organization_results['errors'].append(f"Failed to create folder {target_folder}: {str(e)}")
                continue
            
            # Only move large versions to museum folders (in museumsklar subfolder)
            token = file_pair['large']['token']
            filename = file_pair['large']['filename']
            
            # Get image data (but don't pop it yet, we need it for download too)
            image_data = _IMAGE_STORE.get(token)
            if not image_data:
                organization_results['errors'].append(f"No image data found for {filename}")
                continue
            
            # Write file to museumsklar subfolder
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
    tab = request.args.get('tab', 'simple')  # Default til simple resize
    
    if request.method == "GET":
        return render_template('resizer.html', 
                             current_page='resizer',
                             active_tab=tab)
    
    # Handle different tabs
    if tab == 'simple':
        return handle_simple_resize()
    elif tab == 'grouping':
        return handle_form_submission()  # Existing functionality
    elif tab == 'individual':
        return handle_individual_submission(request.files.getlist('images'))
    else:
        return handle_form_submission()  # Default fallback

def handle_simple_resize():
    """Handle simple resize - unlimited files, resize to KB target"""
    try:
        files = request.files.getlist('images')
        if not files or not any(f.filename for f in files):
            return render_template('resizer.html', 
                                 current_page='resizer',
                                 active_tab='simple',
                                 error='Ingen billeder uploadet')
        
        print(f"Simple resize processing {len(files)} files (NO LIMIT)")
        
        # Get target size from form (in KB)
        try:
            target_size_kb = int(request.form.get('target_size_kb', 300))
            if target_size_kb < 50 or target_size_kb > 2000:
                target_size_kb = 300
        except ValueError:
            target_size_kb = 300
        
        processed_files = []
        
        for file in files:
            if file and file.filename:
                try:
                    # Read image data
                    image_data = file.read()
                    if len(image_data) == 0:
                        continue
                        
                    # Simple resize to target KB size (keep same filename)
                    resized_image = create_thumbnail(image_data, target_size_kb)
                    image_token = _store_image(resized_image)
                    
                    # Keep original filename
                    filename = file.filename
                    # Ensure .jpg extension
                    if not filename.lower().endswith(('.jpg', '.jpeg')):
                        filename = os.path.splitext(filename)[0] + '.jpg'
                    
                    processed_files.append({
                        'token': image_token,
                        'filename': filename,
                        'original_name': file.filename
                    })
                    
                except Exception as e:
                    print(f"Error processing file {file.filename}: {str(e)}")
                    continue
        
        if not processed_files:
            return render_template('resizer.html',
                                 current_page='resizer',
                                 active_tab='simple',
                                 error='Ingen billeder kunne behandles')
        
        # Store processed files for download
        group_token = _store_group_data({
            'files': processed_files,
            'type': 'simple_resize',
            'settings': {'target_size_kb': target_size_kb}
        })
        
        return render_template('resizer.html',
                             current_page='resizer',
                             active_tab='simple',
                             step='simple_results',
                             processed_files=processed_files,
                             group_token=group_token,
                             target_size_kb=target_size_kb,
                             total_processed=len(processed_files))
                             
    except Exception as e:
        return render_template('resizer.html',
                             current_page='resizer',
                             active_tab='simple',
                             error=f'Fejl ved simpel resize: {str(e)}')

def handle_form_submission():
    """Handle form submission for processing groups or individual images"""
    try:
        # hent uploadede filer
        files = request.files.getlist('images')
        if not files or not any(f.filename for f in files):
            return render_template('resizer.html', 
                                 current_page='resizer',
                                 active_tab='grouping',
                                 error='Ingen billeder uploadet')
        
        # Check if this is individual mode
        individual_mode = request.form.get('individual_mode') == 'true'
        
        if individual_mode:
            return handle_individual_submission(files)
        else:
            # hent grupper data
            groups_data = request.form.get('groups_data')
            if not groups_data:
                return render_template('resizer.html', 
                                     current_page='resizer',
                                     active_tab='grouping',
                                     error='Ingen grupper at behandle')
            return handle_group_submission(files, groups_data)
        
    except Exception as e:
        return render_template('resizer.html', 
                             current_page='resizer',
                             active_tab='grouping',
                             error=f'Uventet fejl: {str(e)}')

def handle_individual_submission(files):
    """Handle individual image processing"""
    try:
        # Get individual data
        individual_data_str = request.form.get('individual_data')
        if not individual_data_str:
            return render_template('resizer.html', 
                                 current_page='resizer',
                                 error='Ingen individuel data at behandle')
        
        import json
        try:
            individual_data = json.loads(individual_data_str)
            if not individual_data:
                raise ValueError("No individual data found")
        except (json.JSONDecodeError, ValueError) as e:
            return render_template('resizer.html', 
                                 current_page='resizer',
                                 error=f'Fejl i individuel data: {str(e)}')
        
        # Get settings
        try:
            small_max_size_kb = int(request.form.get('small_max_size', 300))
            if small_max_size_kb < 50 or small_max_size_kb > 2000:
                small_max_size_kb = 300
        except ValueError:
            small_max_size_kb = 300
            
        use_aab_prefix = request.form.get('use_aab_prefix') == 'on'
        auto_organize = request.form.get('auto_organize') == 'on'
        
        print(f"Individual processing: {len(files)} files, settings: small_max_size_kb={small_max_size_kb}, use_aab_prefix={use_aab_prefix}, auto_organize={auto_organize}")
        
        # Memory management - limit number of files processed at once
        max_files = 50  # Reduce from potentially unlimited to prevent server errors
        if len(files) > max_files:
            return render_template('resizer.html', 
                                 current_page='resizer',
                                 active_tab='individual',
                                 error=f'For mange billeder! Maks {max_files} billeder ad gangen for at undgå server fejl. Upload færre billeder.')
        
        # Load uploaded files
        uploaded_files = []
        for i, file in enumerate(files):
            if file and file.filename:
                try:
                    image_data = file.read()
                    if len(image_data) > 0:
                        uploaded_files.append(image_data)
                        print(f"Loaded individual file {i}: {file.filename} ({len(image_data)} bytes)")
                    else:
                        print(f"Warning: Empty file {file.filename}")
                except Exception as e:
                    print(f"Error reading file {file.filename}: {str(e)}")
                    return render_template('resizer.html', 
                                         current_page='resizer',
                                         active_tab='individual',
                                         error=f'Fejl ved læsning af fil {file.filename}: {str(e)}')
        
        if not uploaded_files:
            return render_template('resizer.html', 
                                 current_page='resizer',
                                 active_tab='individual',
                                 error='Ingen gyldige billedfiler fundet')
        
        # Process individual images
        processed_files = []
        
        for item in individual_data:
            image_name = item.get('name', '').strip()
            image_index = item.get('index', 0)
            
            if not image_name:
                return render_template('resizer.html', 
                                     current_page='resizer',
                                     error='🏷️ Alle billeder skal have navne!')
            
            if image_index < len(uploaded_files):
                image_data = uploaded_files[image_index]
                
                # Generate filename
                filename = f"AAB {image_name}.jpg" if use_aab_prefix else f"{image_name}.jpg"
                
                # Create small version (compressed)
                small_image = create_thumbnail(image_data, small_max_size_kb)
                small_token = _store_image(small_image)
                
                # Create large version (original quality)
                large_image = resize_image(image_data)
                large_token = _store_image(large_image)
                
                processed_files.append({
                    'small': {'token': small_token, 'filename': filename},
                    'large': {'token': large_token, 'filename': filename}
                })
        
        # Auto-organize files if requested
        organization_results = None
        if auto_organize:
            if os.environ.get('RENDER') or os.environ.get('RAILWAY_ENVIRONMENT'):
                organization_results = {
                    'success': [],
                    'errors': ['🌐 Auto-organisering virker kun lokalt - ikke på cloud servere. Download ZIP-filen i stedet.'],
                    'folders_created': set()
                }
            else:
                try:
                    organization_results = organize_files_to_museum_folders(processed_files)
                except Exception as e:
                    organization_results = {
                        'success': [],
                        'errors': [f'Fejl ved auto-organisering: {str(e)}. Download ZIP-filen i stedet.'],
                        'folders_created': set()
                    }
        
        # Create download option
        group_token = _store_group_data({
            'files': processed_files,
            'settings': {
                'small_max_size_kb': small_max_size_kb,
                'use_aab_prefix': use_aab_prefix
            }
        })
        
        return render_template('resizer.html',
                             current_page='resizer',
                             active_tab='individual',
                             step='results',
                             processed_files=processed_files,
                             group_token=group_token,
                             organization_results=organization_results)
    
    except Exception as e:
        print(f"Individual processing error: {str(e)}")
        return render_template('resizer.html', 
                             current_page='resizer',
                             active_tab='individual',
                             error=f'Fejl ved behandling af individuelle billeder: {str(e)}')

def handle_group_submission(files, groups_data):
    """Handle group-based image processing (existing functionality)"""
    try:
        print(f"Processing {len(files)} files with groups data: {groups_data}")
        
        import json
        try:
            groups = json.loads(groups_data)
            if not groups:
                raise ValueError("No groups found")
        except (json.JSONDecodeError, ValueError) as e:
            return render_template('resizer.html', 
                                 current_page='resizer',
                                 error=f'Fejl i gruppe data: {str(e)}')
        
        # hent settings (only small image settings needed)
        try:
            small_max_size_kb = int(request.form.get('small_max_size', 300))  # KB now
            if small_max_size_kb < 50 or small_max_size_kb > 2000:
                small_max_size_kb = 300
        except ValueError:
            small_max_size_kb = 300
            
        use_aab_prefix = request.form.get('use_aab_prefix') == 'on'
        auto_organize = request.form.get('auto_organize') == 'on'
        
        print(f"Settings: small_max_size_kb={small_max_size_kb}, use_aab_prefix={use_aab_prefix}, auto_organize={auto_organize}")
        
        # Memory management - limit number of files processed at once
        max_files = 50  # Prevent server errors with too many files
        if len(files) > max_files:
            return render_template('resizer.html', 
                                 current_page='resizer',
                                 active_tab='grouping',
                                 error=f'For mange billeder! Maks {max_files} billeder ad gangen for at undgå server fejl. Upload færre billeder.')
        
        # gem lidt data osv
        uploaded_files = []
        for i, file in enumerate(files):
            if file and file.filename:
                try:
                    image_data = file.read()
                    if len(image_data) > 0:
                        uploaded_files.append(image_data)
                        print(f"Loaded file {i}: {file.filename} ({len(image_data)} bytes)")
                    else:
                        print(f"Warning: Empty file {file.filename}")
                except Exception as e:
                    print(f"Error reading file {file.filename}: {str(e)}")
                    return render_template('resizer.html', 
                                         current_page='resizer',
                                         active_tab='grouping',
                                         error=f'Fejl ved læsning af fil {file.filename}: {str(e)}')
        
        if not uploaded_files:
            return render_template('resizer.html', 
                                 current_page='resizer',
                                 active_tab='grouping',
                                 error='Ingen gyldige billedfiler fundet')
        
        
        # Valider at alle grupper har navne
        for group in groups:
            group_name = group.get('name', '').strip()
            if not group_name or group_name == 'unnamed' or group_name.lower() == 'gruppe':
                return render_template('resizer.html', 
                                     current_page='resizer',
                                     error='🏷️ Alle grupper skal have navne! Husk at navngive dine grupper før behandling.')
        
        processed_files = []
        
        for group in groups:
            group_name = group.get('name', '').strip()
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
        
        # Auto-organize files if requested (only works locally, not on Render)
        organization_results = None
        if auto_organize:
            # Check if we're running on Render (no access to network drives)
            if os.environ.get('RENDER') or os.environ.get('RAILWAY_ENVIRONMENT'):
                organization_results = {
                    'success': [],
                    'errors': ['🌐 Auto-organisering virker kun lokalt - ikke på cloud servere. Download ZIP-filen i stedet.'],
                    'folders_created': set()
                }
            else:
                try:
                    organization_results = organize_files_to_museum_folders(processed_files)
                except Exception as e:
                    organization_results = {
                        'success': [],
                        'errors': [f'Fejl ved auto-organisering: {str(e)}. Download ZIP-filen i stedet.'],
                        'folders_created': set()
                    }
        
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
                             active_tab='grouping',
                             step='results',
                             processed_count=len(processed_files),
                             group_token=group_token,
                             organization_results=organization_results,
                             auto_organized=auto_organize and organization_results and organization_results.get('success'))
                             
    except Exception as e:
        return render_template('resizer.html',
                             current_page='resizer',
                             active_tab='grouping',
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
        
        # Check if we should create museum folder structure
        create_museum_structure = request.args.get('museum_structure') == 'true'
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            
            # Handle different data structures
            if group_data.get('type') == 'simple_resize':
                # Simple resize - single files with same names
                for file_data in group_data['files']:
                    filename = file_data['filename']
                    image_data = _pop_image(file_data['token'])
                    if image_data:
                        zip_file.writestr(filename, image_data)
            else:
                # Regular grouping/individual mode - pairs of small/large
                for file_pair in group_data['files']:
                    filename = file_pair['small']['filename']
                    
                    if create_museum_structure:
                        # Create museum-style folder structure in ZIP
                        case_number = extract_case_number(filename)
                        if case_number:
                            case_folder = get_case_folder_relative(case_number)
                            # Only add large images to case folders (like the real system)
                            large_data = _pop_image(file_pair['large']['token'])
                            if large_data:
                                zip_file.writestr(f"{case_folder}/{filename}", large_data)
                        
                        # Also add regular structure for reference
                        small_data = _pop_image(file_pair['small']['token'])
                        if small_data:
                            zip_file.writestr(f"reference/small/{filename}", small_data)
                        # Large data already used above, get it again if needed
                        large_data = _IMAGE_STORE.get(file_pair['large']['token'])
                        if large_data:
                            zip_file.writestr(f"reference/large/{filename}", large_data)
                    else:
                        # Standard flat structure
                        small_data = _pop_image(file_pair['small']['token'])
                        if small_data:
                            zip_file.writestr(f"small/{filename}", small_data)
                        
                        large_data = _pop_image(file_pair['large']['token'])
                        if large_data:
                            zip_file.writestr(f"large/{filename}", large_data)
        
        zip_buffer.seek(0)
        
        return send_file(
            io.BytesIO(zip_buffer.getvalue()),
            mimetype='application/zip',
            as_attachment=True,
            download_name='processed_images.zip'
        )
        
    except Exception as e:
        return f"Fejl ved download: {str(e)}", 500
