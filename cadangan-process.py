import subprocess
import os
import streamlit as st
from datetime import datetime, timedelta

def parse_timestamp(ts):
    parts = ts.strip().split(":")
    if len(parts) != 4:
        raise ValueError("Format timestamp harus HH:MM:SS:ms")
    hours, minutes, seconds, milliseconds = parts

    if not (hours.isdigit() and minutes.isdigit() and seconds.isdigit() and milliseconds.isdigit()):
        raise ValueError("Semua bagian timestamp harus angka")

    milliseconds = milliseconds.zfill(3)
    return f"{hours}:{minutes}:{seconds}.{milliseconds}"

def calc_duration(start, end):
    fmt = "%H:%M:%S.%f"
    start_dt = datetime.strptime(start, fmt)
    end_dt = datetime.strptime(end, fmt)
    duration = (end_dt - start_dt).total_seconds()
    if duration <= 0:
        raise ValueError("Durasi end harus lebih besar dari start")
    return str(duration)

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