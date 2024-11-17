"""
File: app.py
Description: A Flask application for serving files and directories over HTTP.
Author: juzidaxia
Date: 2024-10-14
usage: python app.py --shared-directory <path_to_shared_directory>
"""

from flask import Flask, render_template, request, send_from_directory, send_file, abort, url_for, after_this_request
import os
import zipfile
import io
import argparse
import mimetypes
from pathlib import Path
import qrcode
import socket
from PIL import Image

app = Flask(__name__)

@app.template_filter('dirname')
def dirname_filter(path):
    return os.path.dirname(path)

def is_safe_path(base_path, target_path):
    # Ensure the target path is within the base path
    return os.path.commonpath([base_path]) == os.path.commonpath([base_path, target_path])

@app.context_processor
def utility_processor():
    return {
        'os': os,
        'dirname_filter': dirname_filter
    }

@app.route('/', methods=['GET'])
def index():
    directory = request.args.get('directory', app.config['SHARED_DIRECTORY'])
    if not is_safe_path(app.config['SHARED_DIRECTORY'], directory):
        abort(403)  # Forbidden

    try:
        # List directory contents with details
        files = []
        for f in os.listdir(directory):
            file_path = os.path.join(directory, f)
            is_dir = os.path.isdir(file_path)
            mime_type, _ = mimetypes.guess_type(file_path)
            can_preview = mime_type is not None and not is_dir
            files.append({
                'name': f,
                'is_dir': is_dir,
                'can_preview': can_preview
            })
        return render_template('index.html', files=files, directory=directory, app=app)
    except FileNotFoundError:
        return "Directory not found.", 404
    except Exception as e:
        return str(e), 500

@app.route('/download', methods=['GET'])
def download_file():
    directory = request.args.get('directory', app.config['SHARED_DIRECTORY'])
    if not is_safe_path(app.config['SHARED_DIRECTORY'], directory):
        abort(403)  # Forbidden

    filename = request.args.get('filename', None)
    if not filename:
        return "Filename not specified.", 400

    try:
        return send_from_directory(
            directory, 
            filename, 
            as_attachment=True,
            max_age=0
        )
    except ConnectionError:
        return "", 204  # Client disconnected
    except FileNotFoundError:
        return "File not found.", 404
    except Exception as e:
        app.logger.error(f"Download error: {str(e)}")
        return str(e), 500

@app.route('/preview', methods=['GET'])
def preview_file():
    directory = request.args.get('directory', app.config['SHARED_DIRECTORY'])
    if not is_safe_path(app.config['SHARED_DIRECTORY'], directory):
        abort(403)  # Forbidden

    filename = request.args.get('filename', None)
    if filename:
        file_path = os.path.join(directory, filename)
        mime_type, _ = mimetypes.guess_type(file_path)
        
        if mime_type:
            try:
                return send_from_directory(directory, filename, as_attachment=False, mimetype=mime_type)
            except FileNotFoundError:
                return "File not found.", 404
            except Exception as e:
                return str(e), 500
        else:
            return "Unable to determine file type for preview.", 400
    return "Filename not specified.", 400

def generate_qr_code(url):
    qr = qrcode.make(url)
    qr_image = qr.convert("RGB")  # Convert to a format that can be displayed
    qr_image.show()

@app.route('/download_selected', methods=['POST'])
def download_selected():
    directory = request.form.get('directory', app.config['SHARED_DIRECTORY'])
    if not is_safe_path(app.config['SHARED_DIRECTORY'], directory):
        abort(403)  # Forbidden

    selected_files = request.form.getlist('selected_files')
    if not selected_files:
        return "No files selected.", 400

    try:
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for filename in selected_files:
                file_path = os.path.join(directory, filename)
                if os.path.exists(file_path):
                    try:
                        zf.write(file_path, filename)
                    except ConnectionError:
                        return "", 204  # Client disconnected
        memory_file.seek(0)

        zip_filename = "selected_files.zip"
        return send_file(memory_file, download_name=zip_filename, as_attachment=True)
    except Exception as e:
        return str(e), 500

@app.route('/download_folder', methods=['GET'])
def download_folder():
    directory = request.args.get('directory', app.config['SHARED_DIRECTORY'])
    foldername = request.args.get('foldername')
    
    if not is_safe_path(app.config['SHARED_DIRECTORY'], directory):
        abort(403)  # Forbidden
        
    folder_path = os.path.join(directory, foldername)
    if not os.path.isdir(folder_path):
        abort(404)  # Not Found

    try:
        # Create a zip file in memory
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    zf.write(file_path, os.path.relpath(file_path, folder_path))
        memory_file.seek(0)
        
        # Use the directory name as the download name
        folder_name = os.path.basename(os.path.normpath(folder_path))
        zip_filename = f"{folder_name}.zip"
        
        return send_file(memory_file, download_name=zip_filename, as_attachment=True)
    except Exception as e:
        return str(e), 500

@app.errorhandler(Exception)
def handle_exception(e):
    # Don't handle client disconnects as errors
    if isinstance(e, ConnectionError):
        return "", 204  # Return empty response with "No Content" status
    raise e  # Re-raise other exceptions

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the Flask file server.')
    parser.add_argument('--host', default='0.0.0.0', help='The host IP address to bind to.')
    parser.add_argument('--port', type=int, default=9527, help='The port number to bind to.')
    parser.add_argument('--shared-directory', default='.', help='The directory to share.')
    args = parser.parse_args()

    app.config['SHARED_DIRECTORY'] = os.path.abspath(args.shared_directory)

    # Get the local IP address
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    # generate_qr_code(f"http://{local_ip}:{args.port}")

    app.run(host=args.host, port=args.port, debug=True)
