import streamlit as st
import process
import os
import subprocess
import requests
import tempfile
from urllib.parse import urlparse
import yt_dlp
import re
import shutil # <--- TAMBAHKAN IMPORT INI

# Daftar folder yang akan dibersihkan
if 'initialized' not in st.session_state:
    # Daftar folder yang akan dibersihkan
    FOLDERS_TO_CLEAR = ["output", "uploads", "previews"]

    for folder in FOLDERS_TO_CLEAR:
        if os.path.exists(folder):
            shutil.rmtree(folder)
        os.makedirs(folder, exist_ok=True)
    
    # Tandai bahwa sesi ini sudah diinisialisasi agar kode ini tidak berjalan lagi
    st.session_state['initialized'] = True

st.title("🎬 AI Short Generator")

# Inisialisasi session state
if 'video_path' not in st.session_state:
    st.session_state['video_path'] = None
if 'video_url' not in st.session_state:
    st.session_state['video_url'] = None
if 'cuts' not in st.session_state:
    st.session_state['cuts'] = [{'start': '00:00:00:000', 'end': '00:00:00:000'}]
if 'video_b_path' not in st.session_state:
    st.session_state['video_b_path'] = None
if 'video_b_url' not in st.session_state:
    st.session_state['video_b_url'] = None
if 'cuts_b' not in st.session_state:
    st.session_state['cuts_b'] = [{'start': '00:00:00:000', 'end': '00:00:00:000'}]
if 'merge_mode' not in st.session_state:
    st.session_state['merge_mode'] = 'Manual'

def is_youtube_url(url):
    """Check if URL is from YouTube"""
    youtube_patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
        r'(?:https?://)?(?:www\.)?youtu\.be/[\w-]+',
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/[\w-]+',
        r'(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+',
    ]
    return any(re.match(pattern, url) for pattern in youtube_patterns)

def is_social_media_url(url):
    """Check if URL is from social media platforms"""
    social_patterns = [
        r'(?:https?://)?(?:www\.)?instagram\.com',
        r'(?:https?://)?(?:www\.)?tiktok\.com',
        r'(?:https?://)?(?:www\.)?twitter\.com',
        r'(?:https?://)?(?:www\.)?x\.com',
        r'(?:https?://)?(?:www\.)?facebook\.com',
        r'(?:https?://)?(?:www\.)?fb\.watch',
    ]
    return any(re.search(pattern, url) for pattern in social_patterns)

def get_video_url_with_yt_dlp(url):
    """
    Mendapatkan direct video URL menggunakan yt-dlp tanpa download
    """
    try:
        ydl_opts = {
            'format': 'best[ext=mp4][height<=1080]/best[height<=1080]/best',
            'noplaylist': True,
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info.get('url')
            title = info.get('title', 'video')
            duration = info.get('duration', 0)
            
            if video_url:
                return video_url, title, duration, None
            else:
                return None, None, None, "Tidak bisa mendapatkan direct video URL"
                
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "Video unavailable" in error_msg:
            return None, None, None, "Video tidak tersedia atau private"
        elif "Sign in to confirm your age" in error_msg:
            return None, None, None, "Video memerlukan verifikasi umur"
        elif "Private video" in error_msg:
            return None, None, None, "Video private, tidak bisa diakses"
        else:
            return None, None, None, f"Error yt-dlp: {error_msg}"
    except Exception as e:
        return None, None, None, f"Error: {str(e)}"

def validate_direct_url(url):
    """
    Validasi URL langsung untuk video
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Range': 'bytes=0-1024'  # Hanya ambil 1KB pertama untuk test
        }
        
        response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
        content_type = response.headers.get('content-type', '').lower()
        
        # Cek apakah server mendukung range requests (penting untuk seeking)
        accept_ranges = response.headers.get('accept-ranges', '').lower()
        
        if 'video/' in content_type or 'application/octet-stream' in content_type:
            return True, accept_ranges == 'bytes'
        else:
            return False, False
            
    except Exception as e:
        return False, False

def download_video_with_yt_dlp(url):
    """
    Download video menggunakan yt-dlp untuk YouTube dan platform lainnya
    (Fungsi asli dipertahankan untuk backward compatibility)
    """
    try:
        os.makedirs("uploads", exist_ok=True)
        
        ydl_opts = {
            'format': 'best[ext=mp4][height<=1080]/best[height<=1080]/best',
            'outtmpl': 'uploads/%(title)s.%(ext)s',
            'restrictfilenames': True,
            'noplaylist': True,
        }
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        def progress_hook(d):
            if d['status'] == 'downloading':
                if 'total_bytes' in d:
                    progress = d['downloaded_bytes'] / d['total_bytes']
                    progress_bar.progress(progress)
                    downloaded_mb = d['downloaded_bytes'] / (1024*1024)
                    total_mb = d['total_bytes'] / (1024*1024)
                    status_text.text(f"Downloading: {downloaded_mb:.1f} MB / {total_mb:.1f} MB")
                else:
                    status_text.text(f"Downloading: {d['downloaded_bytes'] / (1024*1024):.1f} MB")
            elif d['status'] == 'finished':
                progress_bar.progress(1.0)
                status_text.text("Download selesai, memproses...")
                
        ydl_opts['progress_hooks'] = [progress_hook]
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'video')
            ydl.download([url])
            
            expected_filename = ydl.prepare_filename(info)
            if os.path.exists(expected_filename):
                progress_bar.empty()
                status_text.empty()
                return expected_filename, None
            else:
                for file in os.listdir("uploads"):
                    if file.startswith(title.replace(' ', '_')[:20]):
                        file_path = os.path.join("uploads", file)
                        progress_bar.empty()
                        status_text.empty()
                        return file_path, None
                
                progress_bar.empty()
                status_text.empty()
                return None, "File berhasil didownload tapi tidak ditemukan"
                
    except Exception as e:
        st.error(f"Error download: {str(e)}")
        return None, str(e)

# Pilihan metode input
input_method = st.radio(
    "Pilih metode input video:",
    ["📁 Upload File", "🌐 URL Video (Direct Clip)", "🌐 Download dari URL"],
    horizontal=True
)

if input_method == "📁 Upload File":
    uploaded_file = st.file_uploader("Upload file video (mp4/mkv/webm):", type=['mp4', 'mkv', 'webm'])

    if uploaded_file is not None:
        os.makedirs("uploads", exist_ok=True)
        file_path = os.path.join("uploads", uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.session_state['video_path'] = file_path
        st.session_state['video_url'] = None  # Reset URL
        st.success(f"✅ File berhasil di-upload: {uploaded_file.name}")

elif input_method == "🌐 URL Video (Direct Clip)":
    # Mode baru: Direct clip dari URL tanpa download
    video_url = st.text_input(
        "Masukkan URL video untuk direct clipping:",
        placeholder="https://youtu.be/ZApd2Iyfduk atau https://example.com/video.mp4",
        help="Mode ini akan langsung memotong video dari URL tanpa download penuh"
    )
    
    if video_url:
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if st.button("🔍 Validasi URL"):
                with st.spinner("Memvalidasi URL..."):
                    if is_youtube_url(video_url) or is_social_media_url(video_url):
                        # Untuk platform sosial media, ambil direct URL
                        direct_url, title, duration, error = get_video_url_with_yt_dlp(video_url)
                        if direct_url:
                            st.session_state['video_url'] = direct_url
                            st.session_state['video_path'] = None  # Reset file path
                            st.success(f"✅ URL siap untuk direct clipping!")
                            st.info(f"📹 **Judul:** {title}")
                            if duration:
                                hours = duration // 3600
                                minutes = (duration % 3600) // 60
                                seconds = duration % 60
                                st.info(f"⏱️ **Durasi:** {hours:02d}:{minutes:02d}:{seconds:02d}")
                        else:
                            st.error(f"❌ Gagal mendapatkan direct URL: {error}")
                    else:
                        # Untuk direct URL, validasi langsung
                        is_valid, supports_ranges = validate_direct_url(video_url)
                        if is_valid:
                            st.session_state['video_url'] = video_url
                            st.session_state['video_path'] = None  # Reset file path
                            st.success("✅ URL valid dan siap untuk direct clipping!")
                            if supports_ranges:
                                st.info("🚀 Server mendukung range requests - clipping akan optimal!")
                            else:
                                st.warning("⚠️ Server tidak mendukung range requests - clipping mungkin lebih lambat")
                        else:
                            st.error("❌ URL tidak valid atau bukan file video")
        
        with col2:
            st.write("")  # spacing
            if st.button("📥 Fallback Download"):
                st.info("Beralih ke mode download tradisional...")
                with st.spinner("Mendownload video dari URL..."):
                    if is_youtube_url(video_url) or is_social_media_url(video_url):
                        file_path, error = download_video_with_yt_dlp(video_url)
                    else:
                        file_path, error = download_video_from_url(video_url)
                    
                    if file_path:
                        st.session_state['video_path'] = file_path
                        st.session_state['video_url'] = None  # Reset URL
                        filename = os.path.basename(file_path)
                        st.success(f"✅ Video berhasil didownload: {filename}")
                    else:
                        st.error(f"❌ Gagal download video: {error}")

elif input_method == "🌐 Download dari URL":
    # Mode lama: Download penuh dulu
    col1, col2 = st.columns([4, 1])
    
    with col1:
        video_url = st.text_input(
            "Masukkan URL video:",
            placeholder="https://youtu.be/ZApd2Iyfduk atau https://example.com/video.mp4",
            help="Support: YouTube, Instagram, TikTok, Twitter/X, Facebook, atau direct video links"
        )
    
    with col2:
        st.write("")
        st.write("")
        download_button = st.button("⬇️ Download")
    
    if download_button and video_url:
        with st.spinner("Mendownload video dari URL..."):
            if is_youtube_url(video_url) or is_social_media_url(video_url):
                file_path, error = download_video_with_yt_dlp(video_url)
            else:
                file_path, error = download_video_from_url(video_url)
            
            if file_path:
                st.session_state['video_path'] = file_path
                st.session_state['video_url'] = None  # Reset URL
                filename = os.path.basename(file_path)
                st.success(f"✅ Video berhasil didownload: {filename}")
            else:
                st.error(f"❌ Gagal download video: {error}")

# Function download_video_from_url tetap sama seperti kode asli
def download_video_from_url(url, filename=None):
    """Download video dari URL - function asli dipertahankan"""
    # ... (kode asli download_video_from_url)
    pass

# Preview section
if st.session_state.get('preview_path'):
    st.subheader("👀 Preview")
    try:
        video_file = open(st.session_state['preview_path'], 'rb')
        video_bytes = video_file.read()
        st.video(video_bytes)
        video_file.close()
    except FileNotFoundError:
        st.error("File preview tidak ditemukan. Silakan coba buat preview lagi.")
        st.session_state['preview_path'] = None

# Main processing section
if st.session_state.get('video_path') or st.session_state.get('video_url'):
    video_source = st.session_state.get('video_path') or st.session_state.get('video_url')
    is_url_mode = st.session_state.get('video_url') is not None

    if is_url_mode:
        st.info("🌐 **Mode Direct Clipping** - Video akan dipotong langsung dari URL")
    else:
        st.info("📁 **Mode File** - Menggunakan file yang sudah diupload")

    st.subheader("🎯 Tentukan Potongan Video")

    for i, cut in enumerate(st.session_state['cuts']):
        st.write(f"🎞️ Scene {i+1}")
        col1, col2, col3, col4 = st.columns([3, 3, 1, 2])
        cut['start'] = col1.text_input(f"Start (HH:MM:SS:ms) Scene {i+1}", value=cut['start'], key=f"start_{i}")
        cut['end'] = col2.text_input(f"End (HH:MM:SS:ms) Scene {i+1}", value=cut['end'], key=f"end_{i}")
        
        if col3.button("🗑️", key=f"delete_{i}"):
            st.session_state['cuts'].pop(i)
            st.rerun()
            
        with col4:
            st.write("")
            st.write("")
            if st.button("Preview", key=f"preview_{i}"):
                with st.spinner(f"Membuat preview untuk Scene {i+1}..."):
                    if is_url_mode:
                        preview_file_path = process.generate_preview_from_url(video_source, cut)
                    else:
                        preview_file_path = process.generate_preview(video_source, cut)
                    
                    if preview_file_path:
                        st.session_state['preview_path'] = preview_file_path
                    else:
                        st.session_state['preview_path'] = None
                st.rerun()

    if st.button("➕ Tambah Scene"):
        st.session_state['cuts'].append({'start': '00:00:00:000', 'end': '00:00:00:000'})

    crop_mode = st.selectbox(
        "🖼️ Pilih Mode Output",
        [
            "Potrait (Landscape Blur, Hitam, Putih)",
            "Potrait (9:16 TikTok Mode)",
            "Potrait Left-Right to Up-Bottom",
            # "Potrait Streamer (Berat)",
            "Potrait Merge 2 Video",
            "Generate Video Overlay"
        ]
    )

    bg_mode = None
    if crop_mode == "Potrait (Landscape Blur, Hitam, Putih)":
        bg_mode = st.selectbox("Pilih Background:", [ "Hitam", "Putih"]) #"Blur (Berat)" bisa ditambahkan,

    # Handle merge mode for URL
    if crop_mode == "Potrait Merge 2 Video":
        st.subheader("🎬 Video Kedua untuk Merge")
        
        # Pilihan mode merge
        st.session_state['merge_mode'] = st.radio(
            "Pilih Mode Merge:",
            ["Manual", "Otomatis"],
            horizontal=True,
            help="Manual: Tentukan timestamp sendiri | Otomatis: Auto-generate clips berdasarkan durasi video pertama"
        )
        
        input_method_b = st.radio(
            "Pilih metode input video kedua:",
            ["📁 Upload File", "🌐 URL Video (Direct)", "🌐 Download dari URL"],
            horizontal=True,
            key="input_method_b"
        )
        
        if input_method_b == "📁 Upload File":
            uploaded_file_b = st.file_uploader("Upload file video kedua (bawah):", type=['mp4', 'mkv', 'webm'])
            if uploaded_file_b is not None:
                file_b_path = os.path.join("uploads", uploaded_file_b.name)
                with open(file_b_path, "wb") as f:
                    f.write(uploaded_file_b.getbuffer())
                st.session_state['video_b_path'] = file_b_path
                st.session_state['video_b_url'] = None
                st.success(f"✅ File video kedua berhasil di-upload: {uploaded_file_b.name}")
        
        elif input_method_b == "🌐 URL Video (Direct)":
            video_url_b = st.text_input(
                "Masukkan URL video kedua:",
                placeholder="https://youtu.be/abc123 atau https://example.com/video2.mp4",
                key="video_url_b"
            )
            
            if video_url_b and st.button("🔍 Validasi URL Kedua"):
                with st.spinner("Memvalidasi URL kedua..."):
                    if is_youtube_url(video_url_b) or is_social_media_url(video_url_b):
                        direct_url_b, title_b, duration_b, error = get_video_url_with_yt_dlp(video_url_b)
                        if direct_url_b:
                            st.session_state['video_b_url'] = direct_url_b
                            st.session_state['video_b_path'] = None
                            st.success(f"✅ URL video kedua siap!")
                            st.info(f"📹 **Judul Video B:** {title_b}")
                            if duration_b:
                                hours_b = duration_b // 3600
                                minutes_b = (duration_b % 3600) // 60
                                seconds_b = duration_b % 60
                                st.info(f"⏱️ **Durasi Video B:** {hours_b:02d}:{minutes_b:02d}:{seconds_b:02d}")
                        else:
                            st.error(f"❌ Gagal: {error}")
                    else:
                        is_valid, _ = validate_direct_url(video_url_b)
                        if is_valid:
                            st.session_state['video_b_url'] = video_url_b
                            st.session_state['video_b_path'] = None
                            st.success("✅ URL video kedua valid!")
                        else:
                            st.error("❌ URL tidak valid")

        # Auto mode settings
        if st.session_state['merge_mode'] == "Otomatis" and (st.session_state.get('video_b_path') or st.session_state.get('video_b_url')):
            st.subheader("⚙️ Pengaturan Mode Otomatis")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("🎬 **Video Kedua (Bawah) - Pengaturan Waktu**")
                video_b_start = st.text_input(
                    "Start dari detik ke (HH:MM:SS):", 
                    value="00:00:00",
                    help="Mulai dari detik berapa untuk menghindari intro/iklan"
                )
                video_b_end = st.text_input(
                    "End sampai detik (HH:MM:SS) - kosong = sampai akhir:", 
                    value="",
                    help="Akhiri di detik berapa untuk menghindari outro/iklan. Kosongkan jika sampai akhir video"
                )
            
            st.info("💡 **Mode Otomatis:** Sistem akan auto-generate clips dari Video B berdasarkan durasi setiap scene di Video A")
        
        # Manual mode - Cuts untuk video kedua
        elif st.session_state['merge_mode'] == "Manual" and (st.session_state.get('video_b_path') or st.session_state.get('video_b_url')):
            st.subheader("🎯 Tentukan Potongan Video Kedua (Bawah)")
            
            for i, cut_b in enumerate(st.session_state['cuts_b']):
                st.write(f"🎞️ Scene {i+1} (Video Bawah)")
                col1, col2, col3 = st.columns([4, 4, 1])
                cut_b['start'] = col1.text_input(f"Start B (HH:MM:SS:ms) Scene {i+1}", value=cut_b['start'], key=f"start_b_{i}")
                cut_b['end'] = col2.text_input(f"End B (HH:MM:SS:ms) Scene {i+1}", value=cut_b['end'], key=f"end_b_{i}")
                if col3.button("🗑️", key=f"delete_b_{i}"):
                    st.session_state['cuts_b'].pop(i)
                    st.rerun()

            if st.button("➕ Tambah Scene Video B"):
                st.session_state['cuts_b'].append({'start': '00:00:00:000', 'end': '00:00:00:000'})
    
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🚀 Potong Video"):
            with st.spinner("Memproses potongan video..."):
                if crop_mode == "Potrait Merge 2 Video":
                    video_a_source = st.session_state.get('video_path') or st.session_state.get('video_url')
                    video_b_source = st.session_state.get('video_b_path') or st.session_state.get('video_b_url')
                    
                    if st.session_state['merge_mode'] == "Otomatis":
                        # Mode otomatis
                        process.manual_cut_merge_auto(
                            video_a_source,
                            st.session_state['cuts'],
                            video_b_source,
                            is_url_a=st.session_state.get('video_url') is not None,
                            is_url_b=st.session_state.get('video_b_url') is not None,
                            video_b_start=video_b_start,
                            video_b_end=video_b_end if video_b_end else None
                        )
                    else:
                        # Mode manual
                        process.manual_cut_merge_direct(
                            video_a_source,
                            st.session_state['cuts'],
                            video_b_source,
                            st.session_state['cuts_b'],
                            is_url_a=st.session_state.get('video_url') is not None,
                            is_url_b=st.session_state.get('video_b_url') is not None
                        )
                
                elif crop_mode == "Generate Video Overlay":
                    background_path = "background_1080x1920.png"
                    if is_url_mode:
                        process.overlay_to_laptop_direct(background_path, video_source, st.session_state['cuts'])
                    else:
                        process.overlay_to_laptop(background_path, video_source, st.session_state['cuts'])

                else:
                    if is_url_mode:
                        process.manual_cut_direct(
                            video_source,
                            st.session_state['cuts'],
                            crop_mode,
                            bg_mode=bg_mode
                        )
                    else:
                        process.manual_cut(
                            video_source,
                            st.session_state['cuts'],
                            crop_mode,
                            bg_mode=bg_mode
                        )
    
    # with col2:
    #     if st.button("📂 Buka Folder Output"):
    #         output_path = os.path.abspath("output")
    #         subprocess.Popen(f'explorer "{output_path}"')

    # with col3:
    #     if st.button("📂 Buka Folder Uploads"):
    #         folder_path = os.path.abspath("uploads")
    #         subprocess.Popen(f'explorer "{folder_path}"')

output_dir = "output"

# Tampilkan seluruh bagian ini HANYA JIKA folder 'output' ada dan berisi file
if os.path.exists(output_dir) and len(os.listdir(output_dir)) > 0:
    
    st.subheader("📁 File Hasil") # Judul sekarang hanya muncul jika ada file
    
    # Urutkan file agar tampil rapi
    for filename in sorted(os.listdir(output_dir)):
        file_path = os.path.join(output_dir, filename)
        if os.path.isfile(file_path):
            st.write(f"✅ **{filename}**")
            with open(file_path, "rb") as f:
                st.download_button(
                    label="⬇️ Download Video Ini",
                    data=f,
                    file_name=filename,
                    mime="video/mp4"
                )
            st.divider()