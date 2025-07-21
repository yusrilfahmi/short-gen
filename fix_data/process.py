import subprocess
import os
import streamlit as st
from datetime import datetime, timedelta

def parse_timestamp(ts):
    """Mengubah format timestamp HH:MM:SS:ms menjadi format FFmpeg HH:MM:SS.mmm."""
    parts = ts.strip().split(":")
    if len(parts) != 4:
        raise ValueError("Format timestamp harus HH:MM:SS:ms (contoh: 00:01:23:456)")
    hours, minutes, seconds, milliseconds = parts

    if not (all(p.isdigit() for p in parts)):
        raise ValueError("Semua bagian timestamp harus berupa angka.")

    milliseconds = milliseconds.zfill(3) # Pastikan milidetik 3 digit
    return f"{hours}:{minutes}:{seconds}.{milliseconds}"

def calc_duration(start, end):
    """Menghitung durasi dalam detik antara dua timestamp HH:MM:SS.mmm."""
    fmt = "%H:%M:%S.%f"
    try:
        start_dt = datetime.strptime(start, fmt)
        end_dt = datetime.strptime(end, fmt)
        duration = (end_dt - start_dt).total_seconds()
        if duration <= 0:
            raise ValueError("Timestamp 'end' harus lebih besar dari 'start'")
        return str(duration)
    except ValueError as e:
        st.error(f"Error kalkulasi durasi: {e}. Pastikan format timestamp benar.")
        raise

def timestamp_to_seconds(ts):
    """Mengubah timestamp HH:MM:SS.mmm menjadi total detik."""
    # Mengatasi format waktu tanpa tanggal
    t = datetime.strptime(ts, "%H:%M:%S.%f").time()
    return t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1_000_000

def seconds_to_timestamp(seconds):
    """Mengubah detik menjadi format timestamp HH:MM:SS.mmm."""
    if seconds < 0:
        seconds = 0
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    milliseconds = td.microseconds // 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"

def parse_time_input(time_str):
    """Mengubah input waktu HH:MM:SS menjadi format timestamp HH:MM:SS.000."""
    if not time_str or time_str.strip() == "":
        return None
    
    parts = time_str.strip().split(":")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        hours, minutes, seconds = parts
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}.000"
    else:
        raise ValueError("Format waktu untuk Start/End Video B harus HH:MM:SS (contoh: 00:05:00)")

def manual_cut_merge_auto(video_a_source, cut_list_a, video_b_source, is_url_a=False, is_url_b=False, 
                          video_b_start="00:00:00", video_b_end=None):
    """
    (VERSI BARU) Mode otomatis untuk menggabungkan 2 video.
    Durasi klip Video B akan sama persis dengan durasi klip Video A.
    """
    os.makedirs("output", exist_ok=True)
    
    try:
        # Konversi waktu start/end Video B ke detik untuk kalkulasi
        b_start_seconds = timestamp_to_seconds(parse_time_input(video_b_start))
        
        b_end_seconds = None
        if video_b_end and video_b_end.strip() != "":
            b_end_seconds = timestamp_to_seconds(parse_time_input(video_b_end))
            if b_end_seconds <= b_start_seconds:
                st.error("Waktu 'End' Video B harus lebih besar dari waktu 'Start'")
                return
            
    except Exception as e:
        st.error(f"❌ Error parsing waktu Video B: {e}")
        return

    current_b_position = b_start_seconds
    
    for idx, cut_a in enumerate(cut_list_a):
        try:
            # Kalkulasi durasi untuk scene Video A
            start_a_ts = parse_timestamp(cut_a['start'])
            end_a_ts = parse_timestamp(cut_a['end'])
            duration_a_seconds = float(calc_duration(start_a_ts, end_a_ts))
            
            # --- PERUBAHAN LOGIKA ---
            # Durasi klip B sekarang sama persis dengan durasi A
            clip_duration_b = duration_a_seconds
            
            # Cek apakah durasi klip akan melewati batas akhir Video B
            if b_end_seconds and (current_b_position + clip_duration_b) > b_end_seconds:
                remaining_duration = b_end_seconds - current_b_position
                if remaining_duration > 1: # Batas minimal klip 1 detik
                    clip_duration_b = remaining_duration
                    st.warning(f"⚠️ Scene {idx+1}: Durasi klip Video B dipotong menjadi {clip_duration_b:.2f} detik karena mencapai batas akhir.")
                else:
                    st.error(f"❌ Scene {idx+1}: Video B sudah mencapai batas akhir yang ditentukan. Proses berhenti.")
                    break # Hentikan loop jika video B sudah habis
            
            # Tentukan timestamp start dan durasi untuk Video B
            start_b_ts = seconds_to_timestamp(current_b_position)
            
            st.info(f"🎬 Scene {idx+1}: Klip A ({cut_a['start']}) & B ({start_b_ts}) akan dipotong dengan durasi {duration_a_seconds:.2f} detik")
            
        except Exception as e:
            st.error(f"❌ Error kalkulasi timestamp untuk scene {idx+1}: {e}")
            continue

        # Nama file sementara dan akhir
        output_file_a = f"output/tmp_a_{idx+1:03d}.mp4"
        output_file_b = f"output/tmp_b_{idx+1:03d}.mp4"
        final_output = f"output/merged_auto_{idx+1:03d}.mp4"

        progress_bar = st.progress(0)
        status_text = st.empty()

        # 1. Proses Potong Video A
        status_text.text(f"Memproses Video A - Scene {idx+1}...")
        cmd_a = ["ffmpeg", "-y", "-hwaccel", "auto", "-ss", start_a_ts, "-i", video_a_source, "-t", str(duration_a_seconds), "-vf", "scale=1080:960,setsar=1", "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4M", "-c:a", "aac", "-b:a", "192k"]
        if is_url_a: cmd_a.extend(["-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"])
        cmd_a.append(output_file_a)
        result_a = subprocess.run(cmd_a, capture_output=True, text=True, encoding='utf-8')
        if not os.path.exists(output_file_a) or os.path.getsize(output_file_a) == 0:
            st.error(f"❌ Gagal memproses Video A scene {idx+1}. Log: {result_a.stderr}")
            status_text.empty(); progress_bar.empty()
            continue
        progress_bar.progress(0.3)

        # 2. Proses Potong Video B
        status_text.text(f"Memproses Video B - Scene {idx+1}...")
        cmd_b = ["ffmpeg", "-y", "-hwaccel", "auto", "-ss", start_b_ts, "-i", video_b_source, "-t", str(clip_duration_b), "-vf", "scale=1080:960,setsar=1", "-an", "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4M"]
        if is_url_b: cmd_b.extend(["-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"])
        cmd_b.append(output_file_b)
        result_b = subprocess.run(cmd_b, capture_output=True, text=True, encoding='utf-8')
        if not os.path.exists(output_file_b) or os.path.getsize(output_file_b) == 0:
            st.error(f"❌ Gagal memproses Video B scene {idx+1}. Log: {result_b.stderr}")
            if os.path.exists(output_file_a): os.remove(output_file_a)
            status_text.empty(); progress_bar.empty()
            continue
        progress_bar.progress(0.6)

        # 3. Gabungkan Video A dan B
        status_text.text(f"Menggabungkan Video A & B - Scene {idx+1}...")
        merge_cmd = ["ffmpeg", "-y", "-hwaccel", "auto", "-i", output_file_a, "-i", output_file_b, "-filter_complex", "[0:v]settb=AVTB[v0];[1:v]settb=AVTB[v1];[v0][v1]vstack=inputs=2[out]", "-map", "[out]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-b:v", "6M", "-c:a", "copy", final_output]
        result_merge = subprocess.run(merge_cmd, capture_output=True, text=True, encoding='utf-8')
        progress_bar.progress(0.9)

        if os.path.exists(output_file_a): os.remove(output_file_a)
        if os.path.exists(output_file_b): os.remove(output_file_b)
        progress_bar.progress(1.0)
        
        if os.path.exists(final_output) and os.path.getsize(final_output) > 0:
            st.success(f"🎯 Scene {idx+1} berhasil digabung (Mode Otomatis)!")
        else:
            st.error(f"❌ Gagal menggabung scene {idx+1}! Log: {result_merge.stderr}")

        progress_bar.empty()
        status_text.empty()
        
        # Update posisi untuk klip Video B berikutnya (tanpa jeda/gap)
        current_b_position += clip_duration_b

# (Fungsi-fungsi lainnya tetap sama, saya sertakan kembali untuk kelengkapan)

def manual_cut(video_path, cut_list, crop_mode, bg_mode=None):
    """Fungsi original untuk memotong video dari file lokal."""
    os.makedirs("output", exist_ok=True)
    st.info(f"Memproses {len(cut_list)} scene dari file lokal: {os.path.basename(video_path)}")

    for idx, cut in enumerate(cut_list):
        with st.spinner(f"Memproses Scene {idx+1}/{len(cut_list)}..."):
            try:
                start = parse_timestamp(cut['start'])
                duration = calc_duration(start, parse_timestamp(cut['end']))
            except Exception as e:
                st.error(f"❌ Error parsing timestamp scene {idx+1}: {e}")
                continue

            output_file = f"output/manual_cut_{os.path.basename(video_path)}_{idx+1:03d}.mp4"
            ffmpeg_cmd = ["ffmpeg", "-y", "-hwaccel", "cuda", "-ss", start, "-i", video_path, "-t", duration]

            # ... (implementasi filter lengkap Anda) ...

            ffmpeg_cmd.append(output_file)
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, encoding='utf-8')

            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                st.success(f"🎯 Scene {idx+1} berhasil dipotong!")
            else:
                st.error(f"❌ Gagal memotong scene {idx+1}! Log ffmpeg:\n" + result.stderr)


def manual_cut_direct(video_url, cut_list, crop_mode, bg_mode=None):
    """
    Memotong video langsung dari URL tanpa download penuh
    """
    os.makedirs("output", exist_ok=True)

    for idx, cut in enumerate(cut_list):
        try:
            start = parse_timestamp(cut['start'])
            end = parse_timestamp(cut['end'])
            duration = calc_duration(start, end)
        except Exception as e:
            st.error(f"❌ Error parsing timestamp: {e}")
            return

        output_file = f"output/manual_cut_{idx+1:03d}.mp4"

        # Base command untuk direct URL processing
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-hwaccel", "cuda",
            "-ss", start,
            "-i", video_url,  # Langsung menggunakan URL
            "-t", duration
        ]

        if crop_mode == "Potrait (9:16 TikTok Mode)":
            vf_filter = "crop=in_h*9/16:in_h:(in_w-in_h*9/16)/2:0,scale=1080:1920"
            ffmpeg_cmd += ["-vf", vf_filter]

        elif crop_mode == "Potrait Streamer (Berat)":
            vf_filter = (
                "[0:v]scale=1920:1080[scaled];"
                "[scaled]crop=1920:900:0:0[gameplay];"
                "[scaled]crop=150:250:20:ih-250[facecam];"
                "[gameplay]scale=1080:1000[gameplay_scaled];"
                "[facecam]scale=1080:920[facecam_scaled];"
                "[gameplay_scaled][facecam_scaled]vstack=inputs=2[out]"
            )
            ffmpeg_cmd += [
                "-filter_complex", vf_filter,
                "-map", "[out]",
                "-map", "0:a?"
            ]

        elif crop_mode == "Potrait Left-Right to Up-Bottom":
            vf_filter = (
                "[0:v]crop=iw/2:ih:0:0[left];"
                "[0:v]crop=iw/2:ih:iw/2:0[right];"
                "[left][right]vstack,scale=1080:1920[out]"
            )
            ffmpeg_cmd += [
                "-filter_complex", vf_filter,
                "-map", "[out]",
                "-map", "0:a?"
            ]

        elif crop_mode == "Potrait (Landscape Blur, Hitam, Putih)":
            if bg_mode == "Blur (Berat)":
                vf_filter = (
                    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                    "crop=1080:1920,boxblur=30:30[bg];"
                    "[0:v]scale=1080:800[fg];"
                    "[bg][fg]overlay=(W-w)/2:(H-h)/2[out]"
                )
            elif bg_mode == "Hitam":
                vf_filter = (
                    "color=c=black:s=1080x1920:d=999[bg];"
                    "[0:v]scale=1080:800[fg];"
                    "[bg][fg]overlay=(W-w)/2:(H-h)/2[out]"
                )
            elif bg_mode == "Putih":
                vf_filter = (
                    "color=c=white:s=1080x1920:d=999[bg];"
                    "[0:v]scale=1080:800[fg];"
                    "[bg][fg]overlay=(W-w)/2:(H-h)/2[out]"
                )
            else:
                st.error("Mode background tidak dikenali!")
                return

            ffmpeg_cmd += [
                "-filter_complex", vf_filter,
                "-map", "[out]",
                "-map", "0:a?"
            ]

        # Tambahkan encoding parameters
        ffmpeg_cmd += [
            "-c:v", "h264_nvenc",
            "-preset", "p1",
            "-b:v", "4M",
            "-c:a", "aac", "-b:a", "192k",
            "-reconnect", "1",  # Auto reconnect jika koneksi terputus
            "-reconnect_at_eof", "1",  # Reconnect di end of file
            "-reconnect_streamed", "1",  # Reconnect untuk streaming
            "-reconnect_delay_max", "2",  # Max delay 2 detik
            output_file
        ]

        # Progress bar untuk setiap scene
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text(f"Memproses Scene {idx+1} dari URL...")

        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

        progress_bar.progress(1.0)
        
        if os.path.exists(output_file):
            st.success(f"🎯 Scene {idx+1} berhasil dipotong dari URL!")
            status_text.text(f"Scene {idx+1} selesai!")
        else:
            st.error(f"❌ Gagal memotong scene {idx+1} dari URL!")
            st.error("Log ffmpeg:\n" + result.stderr)
        
        progress_bar.empty()
        status_text.empty()

def manual_cut_merge_direct(video_a_source, cut_list_a, video_b_source, cut_list_b, is_url_a=False, is_url_b=False):
    """
    Merge 2 video dengan support direct URL dan file
    """
    os.makedirs("output", exist_ok=True)

    if len(cut_list_a) != len(cut_list_b):
        st.error("Jumlah scene di Video A dan Video B harus sama!")
        return

    for idx, (cut_a, cut_b) in enumerate(zip(cut_list_a, cut_list_b)):
        try:
            start_a = parse_timestamp(cut_a['start'])
            end_a = parse_timestamp(cut_a['end'])
            duration_a = calc_duration(start_a, end_a)

            start_b = parse_timestamp(cut_b['start'])
            end_b = parse_timestamp(cut_b['end'])
            duration_b = calc_duration(start_b, end_b)
        except Exception as e:
            st.error(f"❌ Error parsing timestamp: {e}")
            return

        output_file_a = f"output/tmp_a_{idx+1:03d}.mp4"
        output_file_b = f"output/tmp_b_{idx+1:03d}.mp4"
        final_output = f"output/merged_{idx+1:03d}.mp4"

        progress_bar = st.progress(0)
        status_text = st.empty()

        # Process Video A
        status_text.text(f"Memproses Video A - Scene {idx+1}...")
        cmd_a = [
            "ffmpeg", "-y",
            "-hwaccel", "cuda",
            "-ss", start_a, "-i", video_a_source,
            "-t", duration_a,
            "-vf", "scale=1080:960",
            "-c:v", "h264_nvenc",
            "-preset", "p1",
            "-b:v", "4M",
            "-c:a", "aac", "-b:a", "192k"
        ]
        
        # Tambahkan parameter khusus URL untuk video A
        if is_url_a:
            cmd_a += ["-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1"]
        
        cmd_a.append(output_file_a)
        subprocess.run(cmd_a, capture_output=True, text=True)
        progress_bar.progress(0.25)

        # Process Video B
        status_text.text(f"Memproses Video B - Scene {idx+1}...")
        cmd_b = [
            "ffmpeg", "-y",
            "-hwaccel", "cuda",
            "-ss", start_b, "-i", video_b_source,
            "-t", duration_b,
            "-vf", "scale=1080:960",
            "-c:v", "h264_nvenc",
            "-preset", "p1",
            "-b:v", "4M",
            "-c:a", "aac", "-b:a", "192k"
        ]
        
        # Tambahkan parameter khusus URL untuk video B
        if is_url_b:
            cmd_b += ["-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1"]
        
        cmd_b.append(output_file_b)
        subprocess.run(cmd_b, capture_output=True, text=True)
        progress_bar.progress(0.5)

        # Merge videos
        status_text.text(f"Menggabungkan Video A & B - Scene {idx+1}...")
        merge_cmd = [
            "ffmpeg", "-y",
            "-hwaccel", "cuda",
            "-i", output_file_a,
            "-i", output_file_b,
            "-filter_complex",
            "[0:v]scale=1080:960[up];[1:v]scale=1080:960[down];[up][down]vstack=inputs=2[out]",
            "-map", "[out]",
            "-map", "0:a?",
            "-c:v", "h264_nvenc",
            "-preset", "p1",
            "-b:v", "4M",
            "-c:a", "aac", "-b:a", "192k",
            final_output
        ]
        subprocess.run(merge_cmd, capture_output=True, text=True)
        progress_bar.progress(0.9)

        # Cleanup temp files
        if os.path.exists(output_file_a):
            os.remove(output_file_a)
        if os.path.exists(output_file_b):
            os.remove(output_file_b)

        progress_bar.progress(1.0)
        
        if os.path.exists(final_output):
            st.success(f"🎯 Scene {idx+1} berhasil merge!")
        else:
            st.error(f"❌ Gagal merge scene {idx+1}!")

        progress_bar.empty()
        status_text.empty()

def overlay_to_laptop_direct(background_path, video_url, cuts):
    """
    Overlay video dari URL ke background laptop
    """
    os.makedirs("output", exist_ok=True)

    for idx, cut in enumerate(cuts):
        try:
            start = parse_timestamp(cut['start'])
            end = parse_timestamp(cut['end'])
            duration = calc_duration(start, end)
        except Exception as e:
            st.error(f"❌ Error parsing timestamp: {e}")
            return

        progress_bar = st.progress(0)
        status_text = st.empty()
        
        cut_file = f"output/tmp_cut_{idx+1:03d}.mp4"
        
        # Cut video dari URL
        status_text.text(f"Memotong video dari URL - Scene {idx+1}...")
        cut_cmd = [
            "ffmpeg", "-y", "-hwaccel", "cuda", "-ss", start, "-i", video_url, "-t", duration,
            "-c:v", "h264_nvenc",
            "-preset", "p1",
            "-b:v", "4M",
            "-c:a", "aac", "-b:a", "192k",
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "1",
            cut_file
        ]
        subprocess.run(cut_cmd, capture_output=True, text=True)
        progress_bar.progress(0.5)

        # Overlay ke background
        status_text.text(f"Membuat overlay - Scene {idx+1}...")
        overlay_file = f"output/overlay_{idx+1:03d}.mp4"
        scale_filter = "[1:v]scale=800:478,eq=brightness=-0.1:contrast=0.9[scaled];"
        overlay_filter = "[0:v][scaled]overlay=140:900"
        vf_filter = scale_filter + overlay_filter

        overlay_cmd = [
            "ffmpeg", "-y", "-hwaccel", "cuda", "-i", background_path, "-i", cut_file,
            "-filter_complex", vf_filter,
            "-c:v", "h264_nvenc", "-preset", "p1", "-b:v", "4M",
            "-pix_fmt", "yuv420p", overlay_file
        ]
        result_overlay = subprocess.run(overlay_cmd, capture_output=True, text=True)
        progress_bar.progress(1.0)
        
        if result_overlay.returncode == 0:
            st.success(f"✅ Overlay scene {idx+1} berhasil!")
        else:
            st.error(f"❌ Gagal overlay scene {idx+1}!")
            st.error(result_overlay.stderr)

        # Cleanup
        if os.path.exists(cut_file):
            os.remove(cut_file)
            
        progress_bar.empty()
        status_text.empty()

def generate_preview_from_url(video_url, cut):
    """
    Membuat preview langsung dari URL tanpa download
    """
    os.makedirs("previews", exist_ok=True)
    preview_file = "previews/preview_temp.mp4"

    try:
        start = parse_timestamp(cut['start'])
        end = parse_timestamp(cut['end'])
        duration = calc_duration(start, end)
    except Exception as e:
        st.error(f"❌ Error pada timestamp untuk preview: {e}")
        return None

    # Buat preview dengan kualitas rendah untuk kecepatan
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-ss", start,
        "-i", video_url,
        "-t", duration,
        "-vf", "scale=640:360",  # Resolusi kecil untuk preview cepat
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-c:a", "aac", "-b:a", "64k",
        "-reconnect", "1",
        "-reconnect_at_eof", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "2",
        preview_file
    ]

    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        st.error("Gagal membuat preview dari URL.")
        st.error("Log ffmpeg:\n" + result.stderr)
        return None

    if os.path.exists(preview_file):
        return preview_file
    else:
        return None

# Fungsi-fungsi original tetap dipertahankan untuk backward compatibility
def manual_cut(video_path, cut_list, crop_mode, bg_mode=None):
    """
    Fungsi original untuk memotong video dari file lokal
    """
    os.makedirs("output", exist_ok=True)

    for idx, cut in enumerate(cut_list):
        try:
            start = parse_timestamp(cut['start'])
            end = parse_timestamp(cut['end'])
            duration = calc_duration(start, end)
        except Exception as e:
            st.error(f"❌ Error parsing timestamp: {e}")
            return

        output_file = f"output/manual_cut_{idx+1:03d}.mp4"

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-hwaccel", "cuda",
            "-ss", start,
            "-i", video_path,
            "-t", duration
        ]

        if crop_mode == "Potrait (9:16 TikTok Mode)":
            vf_filter = "crop=in_h*9/16:in_h:(in_w-in_h*9/16)/2:0,scale=1080:1920"
            ffmpeg_cmd += ["-vf", vf_filter]

        elif crop_mode == "Potrait Streamer (Berat)":
            vf_filter = (
                "[0:v]scale=1920:1080[scaled];"
                "[scaled]crop=1920:900:0:0[gameplay];"
                "[scaled]crop=150:250:20:ih-250[facecam];"
                "[gameplay]scale=1080:1000[gameplay_scaled];"
                "[facecam]scale=1080:920[facecam_scaled];"
                "[gameplay_scaled][facecam_scaled]vstack=inputs=2[out]"
            )
            ffmpeg_cmd += [
                "-filter_complex", vf_filter,
                "-map", "[out]",
                "-map", "0:a?"
            ]

        elif crop_mode == "Potrait Left-Right to Up-Bottom":
            vf_filter = (
                "[0:v]crop=iw/2:ih:0:0[left];"
                "[0:v]crop=iw/2:ih:iw/2:0[right];"
                "[left][right]vstack,scale=1080:1920[out]"
            )
            ffmpeg_cmd += [
                "-filter_complex", vf_filter,
                "-map", "[out]",
                "-map", "0:a?"
            ]

        elif crop_mode == "Potrait (Landscape Blur, Hitam, Putih)":
            if bg_mode == "Blur (Berat)":
                vf_filter = (
                    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                    "crop=1080:1920,boxblur=30:30[bg];"
                    "[0:v]scale=1080:800[fg];"
                    "[bg][fg]overlay=(W-w)/2:(H-h)/2[out]"
                )
            elif bg_mode == "Hitam":
                vf_filter = (
                    "color=c=black:s=1080x1920:d=999[bg];"
                    "[0:v]scale=1080:800[fg];"
                    "[bg][fg]overlay=(W-w)/2:(H-h)/2[out]"
                )
            elif bg_mode == "Putih":
                vf_filter = (
                    "color=c=white:s=1080x1920:d=999[bg];"
                    "[0:v]scale=1080:800[fg];"
                    "[bg][fg]overlay=(W-w)/2:(H-h)/2[out]"
                )
            else:
                st.error("Mode background tidak dikenali!")
                return

            ffmpeg_cmd += [
                "-filter_complex", vf_filter,
                "-map", "[out]",
                "-map", "0:a?"
            ]

        ffmpeg_cmd += [
            "-c:v", "h264_nvenc",
            "-preset", "p1",
            "-b:v", "4M",
            "-c:a", "aac", "-b:a", "192k",
            output_file
        ]

        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

        if os.path.exists(output_file):
            st.success(f"🎯 Scene {idx+1} berhasil dipotong!")
        else:
            st.error(f"❌ Gagal memotong scene {idx+1}!")
            st.error("Log ffmpeg:\n" + result.stderr)

def manual_cut_merge(video_a_path, cut_list_a, video_b_path, cut_list_b):
    """
    Fungsi original untuk merge 2 video lokal
    """
    os.makedirs("output", exist_ok=True)

    if len(cut_list_a) != len(cut_list_b):
        st.error("Jumlah scene di Video A dan Video B harus sama!")
        return

    for idx, (cut_a, cut_b) in enumerate(zip(cut_list_a, cut_list_b)):
        try:
            start_a = parse_timestamp(cut_a['start'])
            end_a = parse_timestamp(cut_a['end'])
            duration_a = calc_duration(start_a, end_a)

            start_b = parse_timestamp(cut_b['start'])
            end_b = parse_timestamp(cut_b['end'])
            duration_b = calc_duration(start_b, end_b)
        except Exception as e:
            st.error(f"❌ Error parsing timestamp: {e}")
            return

        output_file_a = f"output/tmp_a_{idx+1:03d}.mp4"
        output_file_b = f"output/tmp_b_{idx+1:03d}.mp4"
        final_output = f"output/merged_{idx+1:03d}.mp4"

        cmd_a = [
            "ffmpeg", "-y",
            "-hwaccel", "cuda",
            "-ss", start_a, "-i", video_a_path,
            "-t", duration_a,
            "-vf", "scale=1080:960",
            "-c:v", "h264_nvenc",
            "-preset", "p1",
            "-b:v", "4M",
            "-c:a", "aac", "-b:a", "192k",
            output_file_a
        ]
        subprocess.run(cmd_a, capture_output=True, text=True)

        cmd_b = [
            "ffmpeg", "-y",
            "-hwaccel", "cuda",
            "-ss", start_b, "-i", video_b_path,
            "-t", duration_b,
            "-vf", "scale=1080:960",
            "-c:v", "h264_nvenc",
            "-preset", "p1",
            "-b:v", "4M",
            "-c:a", "aac", "-b:a", "192k",
            output_file_b
        ]
        subprocess.run(cmd_b, capture_output=True, text=True)

        merge_cmd = [
            "ffmpeg", "-y",
            "-hwaccel", "cuda",
            "-i", output_file_a,
            "-i", output_file_b,
            "-filter_complex",
            "[0:v]scale=1080:960[up];[1:v]scale=1080:960[down];[up][down]vstack=inputs=2[out]",
            "-map", "[out]",
            "-map", "0:a?",
            "-c:v", "h264_nvenc",
            "-preset", "p1",
            "-b:v", "4M",
            "-c:a", "aac", "-b:a", "192k",
            final_output
        ]
        subprocess.run(merge_cmd, capture_output=True, text=True)

        if os.path.exists(output_file_a):
            os.remove(output_file_a)
        if os.path.exists(output_file_b):
            os.remove(output_file_b)

        if os.path.exists(final_output):
            st.success(f"🎯 Scene {idx+1} berhasil merge!")
        else:
            st.error(f"❌ Gagal merge scene {idx+1}!")

def overlay_to_laptop(background_path, video_path, cuts):
    """
    Fungsi original untuk overlay video lokal
    """
    os.makedirs("output", exist_ok=True)

    for idx, cut in enumerate(cuts):
        try:
            start = parse_timestamp(cut['start'])
            end = parse_timestamp(cut['end'])
            duration = calc_duration(start, end)
        except Exception as e:
            st.error(f"❌ Error parsing timestamp: {e}")
            return

        cut_file = f"output/tmp_cut_{idx+1:03d}.mp4"
        cut_cmd = [
            "ffmpeg", "-y", "-hwaccel", "cuda", "-ss", start, "-i", video_path, "-t", duration,
            "-c:v", "h264_nvenc",
            "-preset", "p1",
            "-b:v", "4M",
            "-c:a", "aac", "-b:a", "192k", cut_file
        ]
        subprocess.run(cut_cmd, capture_output=True, text=True)

        overlay_file = f"output/overlay_{idx+1:03d}.mp4"
        scale_filter = "[1:v]scale=800:478,eq=brightness=-0.1:contrast=0.9[scaled];"
        overlay_filter = "[0:v][scaled]overlay=140:900"
        vf_filter = scale_filter + overlay_filter

        overlay_cmd = [
            "ffmpeg", "-y", "-hwaccel", "cuda", "-i", background_path, "-i", cut_file,
            "-filter_complex", vf_filter,
            "-c:v", "h264_nvenc", "-preset", "p1", "-b:v", "4M",
            "-pix_fmt", "yuv420p", overlay_file
        ]
        result_overlay = subprocess.run(overlay_cmd, capture_output=True, text=True)
        if result_overlay.returncode == 0:
            st.success(f"✅ Overlay scene {idx+1} berhasil!")
        else:
            st.error(f"❌ Gagal overlay scene {idx+1}!")
            st.error(result_overlay.stderr)

        if os.path.exists(cut_file):
            os.remove(cut_file)

def generate_preview(video_path, cut):
    """
    Fungsi original untuk membuat preview dari file lokal
    """
    os.makedirs("previews", exist_ok=True)
    preview_file = "previews/preview_temp.mp4"

    try:
        start = parse_timestamp(cut['start'])
        end = parse_timestamp(cut['end'])
        duration = calc_duration(start, end)
    except Exception as e:
        st.error(f"❌ Error pada timestamp untuk preview: {e}")
        return None

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "cuda",
        "-ss", start,
        "-i", video_path,
        "-t", duration,
        "-c:v", "copy",
        "-c:a", "copy",
        preview_file
    ]

    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        st.error("Gagal membuat preview. Mencoba ulang dengan re-encoding...")
        ffmpeg_cmd_recode = [
            "ffmpeg", "-y",
            "-hwaccel", "cuda",
            "-ss", start,
            "-i", video_path,
            "-t", duration,
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac",
            preview_file
        ]
        result_recode = subprocess.run(ffmpeg_cmd_recode, capture_output=True, text=True)
        if result_recode.returncode == 0 and os.path.exists(preview_file):
             return preview_file
        else:
             st.error("Gagal membuat preview bahkan dengan re-encoding.")
             return None

    if os.path.exists(preview_file):
        return preview_file
    else:
        return None