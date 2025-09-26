import streamlit as st
import io
import json
import zipfile
from PIL import Image
import base64

class TextureAtlasPacker:
    def __init__(self, max_size=16384):
        self.max_size = max_size
        self.images = []

    def add_image(self, image_data, name):
        """Добавить изображение в очередь для упаковки"""
        try:
            img = Image.open(image_data)

            # Убедимся что изображение в RGBA формате
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # Обрезаем прозрачные границы
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
            return False, f"Ошибка при загрузке изображения: {e}"

    def pack_textures(self):
        """Упаковать все текстуры в атлас"""
        if not self.images:
            return None, None, "Нет изображений для упаковки"

        # Сортируем изображения по размеру
        self.images.sort(key=lambda x: x['width'] * x['height'], reverse=True)

        # Найдем оптимальный размер атласа
        atlas_width, atlas_height = self._calculate_atlas_size()

        # Создаем пустой атлас
        atlas = Image.new('RGBA', (atlas_width, atlas_height), (0, 0, 0, 0))

        # Упаковываем изображения
        packed_rects = self._pack_rectangles(atlas_width, atlas_height)

        successful_packs = sum(1 for rect in packed_rects if rect['fit'])
        if successful_packs == 0:
            return None, None, "Не удалось упаковать ни одного изображения"

        # Размещаем изображения на атласе
        atlas_info = {}
        for i, rect in enumerate(packed_rects):
            if rect['fit']:
                x, y = rect['fit']['x'], rect['fit']['y']
                img_data = self.images[i]
                atlas.paste(img_data['image'], (x, y), img_data['image'])

                atlas_info[img_data['name']] = {
                    'x': x, 'y': y,
                    'width': img_data['width'],
                    'height': img_data['height']
                }

        status = f"Упаковано {len(atlas_info)} из {len(self.images)} изображений. Размер атласа: {atlas_width}x{atlas_height}"
        return atlas, atlas_info, status

    def _calculate_atlas_size(self):
        """Вычисляем оптимальный размер атласа"""
        total_area = sum(img['width'] * img['height'] for img in self.images)
        size = int((total_area ** 0.5) * 1.3)
        size = self._next_power_of_2(size)
        size = min(size, self.max_size)
        return size, size

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
        else:
            return None

    def _split_node(self, node, w, h):
        node['used'] = True
        node['down'] = {
            'x': node['x'], 'y': node['y'] + h,
            'w': node['w'], 'h': node['h'] - h
        }
        node['right'] = {
            'x': node['x'] + w, 'y': node['y'],
            'w': node['w'] - w, 'h': h
        }
        return node

def get_download_link(file_buffer, filename, text):
    """Создает ссылку для скачивания файла"""
    b64 = base64.b64encode(file_buffer.getvalue()).decode()
    return f'<a href="data:application/octet-stream;base64,{b64}" download="{filename}">{text}</a>'

# Настройка страницы
st.set_page_config(
    page_title="Texture Atlas Packer",
    page_icon="🎨",
    layout="wide"
)

# Заголовок
st.title("🎨 Texture Atlas Packer Online")
st.markdown("**Упаковка PNG изображений с прозрачным фоном в единый атлас**")

# Боковая панель с настройками
st.sidebar.header("⚙️ Настройки")
max_size = st.sidebar.selectbox(
    "Максимальный размер атласа:",
    [4096, 8192, 16384],
    index=2
)

st.sidebar.markdown("---")
st.sidebar.markdown("""
### 📋 Инструкция:
1. Загрузите PNG файлы с прозрачным фоном
2. Нажмите "Упаковать атлас"  
3. Скачайте готовый атлас и JSON

### ⚠️ Требования:
- Только PNG файлы
- Размер файла до 200MB
- Изображения с альфа-каналом
""")

# Инициализация упаковщика
if 'packer' not in st.session_state:
    st.session_state.packer = TextureAtlasPacker(max_size=max_size)
if 'uploaded_files_names' not in st.session_state:
    st.session_state.uploaded_files_names = []

# Обновляем размер если изменился
st.session_state.packer.max_size = max_size

# Основная область
col1, col2 = st.columns([2, 1])

with col1:
    st.header("📤 Загрузка изображений")

    # Загрузчик файлов
    uploaded_files = st.file_uploader(
        "Выберите PNG файлы:",
        type=['png'],
        accept_multiple_files=True,
        key="file_uploader"
    )

    if uploaded_files:
        new_files = []
        for uploaded_file in uploaded_files:
            if uploaded_file.name not in st.session_state.uploaded_files_names:
                new_files.append(uploaded_file)
                st.session_state.uploaded_files_names.append(uploaded_file.name)

        # Добавляем новые файлы
        for uploaded_file in new_files:
            file_buffer = io.BytesIO(uploaded_file.read())
            success, message = st.session_state.packer.add_image(file_buffer, uploaded_file.name)

            if success:
                st.success(message)
            else:
                st.error(message)

    # Показываем текущие изображения
    if st.session_state.packer.images:
        st.subheader(f"📊 Загружено изображений: {len(st.session_state.packer.images)}")

        # Превью изображений
        cols = st.columns(4)
        for i, img_data in enumerate(st.session_state.packer.images[:8]):  # Показываем первые 8
            with cols[i % 4]:
                st.image(img_data['image'], caption=img_data['name'], width=100)
                st.caption(f"{img_data['width']}×{img_data['height']}")

        if len(st.session_state.packer.images) > 8:
            st.caption(f"... и еще {len(st.session_state.packer.images) - 8} изображений")

with col2:
    st.header("🎯 Действия")

    if st.button("🗑️ Очистить все", type="secondary"):
        st.session_state.packer = TextureAtlasPacker(max_size=max_size)
        st.session_state.uploaded_files_names = []
        st.rerun()

    st.markdown("---")

    if st.session_state.packer.images:
        if st.button("📦 Упаковать атлас", type="primary"):
            with st.spinner("Упаковываю атлас..."):
                atlas, atlas_info, status = st.session_state.packer.pack_textures()

                if atlas:
                    st.session_state.atlas = atlas
                    st.session_state.atlas_info = atlas_info
                    st.session_state.status = status
                else:
                    st.error(status)

# Показываем результат
if 'atlas' in st.session_state and st.session_state.atlas:
    st.header("🎉 Результат")
    st.success(st.session_state.status)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🖼️ Готовый атлас")
        st.image(st.session_state.atlas, caption="Texture Atlas", use_column_width=True)

        # Подготавливаем файл атласа для скачивания
        atlas_buffer = io.BytesIO()
        st.session_state.atlas.save(atlas_buffer, format='PNG')

        st.download_button(
            label="💾 Скачать атлас (PNG)",
            data=atlas_buffer.getvalue(),
            file_name="texture_atlas.png",
            mime="image/png"
        )

    with col2:
        st.subheader("📋 Информация об атласе")

        # Показываем JSON в читаемом виде
        st.json(st.session_state.atlas_info)

        # Подготавливаем JSON файл для скачивания
        json_data = json.dumps(st.session_state.atlas_info, indent=2, ensure_ascii=False)

        st.download_button(
            label="💾 Скачать координаты (JSON)",
            data=json_data.encode('utf-8'),
            file_name="atlas_coordinates.json",
            mime="application/json"
        )

    # Создаем ZIP архив с обоими файлами
    st.subheader("📦 Скачать все")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Добавляем атлас
        atlas_buffer = io.BytesIO()
        st.session_state.atlas.save(atlas_buffer, format='PNG')
        zip_file.writestr("texture_atlas.png", atlas_buffer.getvalue())

        # Добавляем JSON
        zip_file.writestr("atlas_coordinates.json", json_data.encode('utf-8'))

    st.download_button(
        label="📦 Скачать ZIP архив",
        data=zip_buffer.getvalue(),
        file_name="texture_atlas_pack.zip",
        mime="application/zip"
    )

# Футер
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>🎨 Texture Atlas Packer Online v1.0 | Создано для 3D художников</p>
</div>
""", unsafe_allow_html=True)
