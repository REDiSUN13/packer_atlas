from flask import Flask, render_template, request, send_file, jsonify
import io
import json
import zipfile
from PIL import Image
import base64
import os

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB max file size

class TextureAtlasPacker:
    def __init__(self, max_size=16384):
        self.max_size = max_size
        self.images = []

    def add_image(self, image_data, name):
        try:
            img = Image.open(image_data)
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)
            else:
                return False, "Изображение полностью прозрачное"

            self.images.append({
                'name': name,
                'image': img,
                'width': img.width,
                'height': img.height
            })
            return True, f"Добавлено: {name} ({img.width}x{img.height})"
        except Exception as e:
            return False, f"Ошибка: {e}"

    def pack_textures(self):
        if not self.images:
            return None, None, "Нет изображений"

        self.images.sort(key=lambda x: x['width'] * x['height'], reverse=True)
        atlas_width, atlas_height = self._calculate_atlas_size()
        atlas = Image.new('RGBA', (atlas_width, atlas_height), (0, 0, 0, 0))
        packed_rects = self._pack_rectangles(atlas_width, atlas_height)

        atlas_info = {}
        for i, rect in enumerate(packed_rects):
            if rect['fit']:
                x, y = rect['fit']['x'], rect['fit']['y']
                img_data = self.images[i]
                atlas.paste(img_data['image'], (x, y), img_data['image'])
                atlas_info[img_data['name']] = {
                    'x': x, 'y': y, 'width': img_data['width'], 'height': img_data['height']
                }

        status = f"Упаковано {len(atlas_info)} из {len(self.images)} изображений"
        return atlas, atlas_info, status

    def _calculate_atlas_size(self):
        total_area = sum(img['width'] * img['height'] for img in self.images)
        size = int((total_area ** 0.5) * 1.3)
        size = self._next_power_of_2(size)
        return min(size, self.max_size), min(size, self.max_size)

    def _next_power_of_2(self, x):
        return 1 if x == 0 else 2**(x - 1).bit_length()

    def _pack_rectangles(self, width, height):
        root = {'x': 0, 'y': 0, 'w': width, 'h': height}
        packed_rects = []
        for img in self.images:
            rect = {'w': img['width'], 'h': img['height']}
            node = self._find_node(root, rect['w'], rect['h'])
            if node:
                rect['fit'] = self._split_node(node, rect['w'], rect['h'])
            else:
                rect['fit'] = None
            packed_rects.append(rect)
        return packed_rects

    def _find_node(self, root, w, h):
        if root.get('used'):
            return (self._find_node(root.get('right'), w, h) or 
                   self._find_node(root.get('down'), w, h))
        elif w <= root['w'] and h <= root['h']:
            return root
        return None

    def _split_node(self, node, w, h):
        node['used'] = True
        node['down'] = {'x': node['x'], 'y': node['y'] + h, 'w': node['w'], 'h': node['h'] - h}
        node['right'] = {'x': node['x'] + w, 'y': node['y'], 'w': node['w'] - w, 'h': h}
        return node

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/pack', methods=['POST'])
def pack_textures():
    try:
        files = request.files.getlist('files')
        max_size = int(request.form.get('max_size', 16384))

        packer = TextureAtlasPacker(max_size=max_size)

        for file in files:
            if file.filename.endswith('.png'):
                file_buffer = io.BytesIO(file.read())
                packer.add_image(file_buffer, file.filename)

        atlas, atlas_info, status = packer.pack_textures()

        if atlas:
            # Сохраняем в ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                atlas_buffer = io.BytesIO()
                atlas.save(atlas_buffer, format='PNG')
                zip_file.writestr('texture_atlas.png', atlas_buffer.getvalue())
                zip_file.writestr('atlas_coordinates.json', 
                                json.dumps(atlas_info, indent=2).encode('utf-8'))

            zip_buffer.seek(0)
            return send_file(zip_buffer, 
                           as_attachment=True, 
                           download_name='texture_atlas_pack.zip',
                           mimetype='application/zip')
        else:
            return jsonify({'error': status}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
