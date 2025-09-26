# pages/resizer.py
import io
import os
import re
import zipfile
from typing import Dict, List, Optional, Tuple
from PIL import Image
from flask import Blueprint, render_template, request, send_file, jsonify
import base64

resizer_bp = Blueprint("resizer", __name__)

# Simple in-memory store for image data (use Redis in production)
_IMAGE_STORE: Dict[str, bytes] = {}
_GROUP_STORE: Dict[str, Dict] = {}

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

def create_thumbnail(image_data: bytes, max_size: int = 300) -> bytes:
    """Create a thumbnail version of the image"""
    image = Image.open(io.BytesIO(image_data))
    
    # Convert to RGB if necessary (for PNG with transparency, etc.)
    if image.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Calculate new size maintaining aspect ratio
    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    
    # Save as JPEG
    output = io.BytesIO()
    image.save(output, format='JPEG', quality=85, optimize=True)
    output.seek(0)
    return output.getvalue()

def resize_image(image_data: bytes, max_size: int = 1920) -> bytes:
    """Resize image if it's larger than max_size"""
    image = Image.open(io.BytesIO(image_data))
    
    # Convert to RGB if necessary
    if image.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Only resize if image is larger than max_size
    if max(image.size) > max_size:
        # Calculate new size maintaining aspect ratio
        ratio = min(max_size / image.width, max_size / image.height)
        new_size = (int(image.width * ratio), int(image.height * ratio))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
    
    # Save as JPEG
    output = io.BytesIO()
    image.save(output, format='JPEG', quality=95, optimize=True)
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
    
    # Handle form submission for processing groups
    return handle_form_submission()

def handle_form_submission():
    """Handle form submission for processing groups"""
    try:
        # Get uploaded files
        files = request.files.getlist('images')
        if not files:
            return render_template('resizer.html', 
                                 current_page='resizer',
                                 error='Ingen billeder uploadet')
        
        # Get form data
        groups_data = request.form.get('groups_data')
        if not groups_data:
            return render_template('resizer.html', 
                                 current_page='resizer',
                                 error='Ingen grupper at behandle')
        
        import json
        groups = json.loads(groups_data)
        
        # Get settings
        small_max_size = int(request.form.get('small_max_size', 300))
        large_max_size = int(request.form.get('large_max_size', 1920))
        use_aab_prefix = request.form.get('use_aab_prefix') == 'on'
        
        # Store uploaded files data
        uploaded_files = []
        for file in files:
            if file and file.filename:
                image_data = file.read()
                uploaded_files.append(image_data)
        
        # Process all groups
        processed_files = []
        
        for group in groups:
            group_name = group.get('name', 'unnamed')
            image_indices = group.get('images', [])
            
            # Generate filenames for this group
            letters = [chr(97 + i) for i in range(len(image_indices))]  # a, b, c, ...
            
            for i, (image_index, letter) in enumerate(zip(image_indices, letters)):
                if image_index < len(uploaded_files):
                    image_data = uploaded_files[image_index]
                    
                    # Generate filename
                    base_name = f"AAB {group_name} {letter}" if use_aab_prefix else f"{group_name} {letter}"
                    
                    # Create small version
                    small_image = create_thumbnail(image_data, small_max_size)
                    small_filename = f"{base_name}_small.jpg"
                    small_token = _store_image(small_image)
                    
                    # Create large version
                    large_image = resize_image(image_data, large_max_size)
                    large_filename = f"{base_name}.jpg"
                    large_token = _store_image(large_image)
                    
                    processed_files.append({
                        'small': {'token': small_token, 'filename': small_filename},
                        'large': {'token': large_token, 'filename': large_filename}
                    })
        
        # Store processed data for download
        group_token = _store_group_data({
            'files': processed_files,
            'settings': {
                'small_max_size': small_max_size,
                'large_max_size': large_max_size,
                'use_aab_prefix': use_aab_prefix
            }
        })
        
        return render_template('resizer.html',
                             current_page='resizer',
                             step='results',
                             processed_count=len(processed_files),
                             group_token=group_token)
                             
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
        
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add all processed files to ZIP
            for file_pair in group_data['files']:
                # Add small version
                small_data = _pop_image(file_pair['small']['token'])
                if small_data:
                    zip_file.writestr(f"small/{file_pair['small']['filename']}", small_data)
                
                # Add large version
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
