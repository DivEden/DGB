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

def create_thumbnail(image_data: bytes, max_size_kb: int = 300) -> bytes:
    """Create a compressed thumbnail with size limit in KB - aims for target size"""
    image = Image.open(io.BytesIO(image_data))
    
    # Convert to RGB if necessary (for PNG with transparency, etc.)
    if image.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Don't resize immediately - try to get target KB size first
    temp_image = image.copy()
    quality = 95
    
    # Binary search-like approach for better KB targeting
    for attempt in range(12):
        output = io.BytesIO()
        temp_image.save(output, format='JPEG', quality=quality, optimize=True)
        size_kb = len(output.getvalue()) / 1024
        
        # If we're close to target (within 15%), accept it
        if size_kb <= max_size_kb and size_kb >= max_size_kb * 0.75:
            output.seek(0)
            return output.getvalue()
        elif size_kb <= max_size_kb:
            # Too small, try higher quality if possible
            if quality < 95:
                quality = min(95, quality + 5)
            else:
                # Already at max quality, accept result
                output.seek(0)
                return output.getvalue()
        else:
            # Too big, reduce quality more gradually
            if quality > 70:
                quality -= 5
            else:
                quality -= 10
        
        # If quality gets very low, resize image and reset quality
        if quality <= 40 and max(temp_image.size) > 600:
            ratio = 0.85
            new_size = (int(temp_image.width * ratio), int(temp_image.height * ratio))
            temp_image = image.resize(new_size, Image.Resampling.LANCZOS)
            quality = 85
            image = temp_image  # Update reference for next resize if needed
    
    # Final save
    output = io.BytesIO()
    temp_image.save(output, format='JPEG', quality=quality, optimize=True)
    output.seek(0)
    return output.getvalue()

def resize_image(image_data: bytes, max_size: int = None) -> bytes:
    """ONLY rename/format convert - NO resizing or quality loss for large images"""
    # For large images, we want to preserve EVERYTHING - just ensure JPEG format
    image = Image.open(io.BytesIO(image_data))
    
    # Only convert format if absolutely necessary
    if image.format == 'JPEG' and image.mode == 'RGB':
        # Already perfect format, return original data unchanged
        return image_data
    
    # Only convert to RGB if necessary (for format consistency)
    if image.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Save with absolute maximum quality and no optimization
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
        
        # Get settings (only small image settings needed)
        small_max_size_kb = int(request.form.get('small_max_size', 300))  # KB now
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
                    
                    # Generate filename (same for both versions)
                    filename = f"AAB {group_name} {letter}.jpg" if use_aab_prefix else f"{group_name} {letter}.jpg"
                    
                    # Create small version (compressed by KB)
                    small_image = create_thumbnail(image_data, small_max_size_kb)
                    small_token = _store_image(small_image)
                    
                    # Create large version (original quality, no resize)
                    large_image = resize_image(image_data)  # No max_size parameter
                    large_token = _store_image(large_image)
                    
                    processed_files.append({
                        'small': {'token': small_token, 'filename': filename},
                        'large': {'token': large_token, 'filename': filename}
                    })
        
        # Store processed data for download
        group_token = _store_group_data({
            'files': processed_files,
            'settings': {
                'small_max_size_kb': small_max_size_kb,
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
