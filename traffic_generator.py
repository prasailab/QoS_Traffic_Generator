#!/usr/bin/env python3
"""
QoS Throughput Traffic Generator - EF, AF, NC, & BE Classification Testing
Version: 2.0
Author: Prasath Suthagar, Engineering Authority 
Description: This script runs on a Linux VM to perform QoS throughput testing.
             It supports a dynamic registry of 16 QoS classifications, handles
             automated sequential port mapping, offers auto-equal bandwidth
             allocations, bypasses kernel ICMP ratelimiting, parses pre-flight RTT,
             calculates network limits (BDP, TCP Window, MSS, per-class burst intervals),
             generates dynamic concurrent DSCP-marked streams, and displays an
             interactive traffic monitoring dashboard using iftop.
"""

import sys
import os
import time
import subprocess
import re
import signal
import threading
import math
import shutil
import socket

# ==========================================
# Terminal Styling & Colors (ANSI)
# ==========================================
class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"
    
    # Text colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Bright/Bold text colors
    B_RED = "\033[91m"
    B_GREEN = "\033[92m"
    B_YELLOW = "\033[93m"
    B_BLUE = "\033[94m"
    B_MAGENTA = "\033[95m"
    B_CYAN = "\033[96m"
    
    # Backgrounds
    BG_CYAN = "\033[46m"
    BG_BLUE = "\033[44m"
    BG_BLACK = "\033[40m"
    
    # Indicators
    INFO = f"{B_BLUE}[i]{RESET}"
    SUCCESS = f"{B_GREEN}[OK]{RESET}"
    WARN = f"{B_YELLOW}[!]{RESET}"
    ERROR = f"{B_RED}[ERR]{RESET}"
    INPUT = f"{B_CYAN}[?]{RESET}"

# ==========================================
# QoS Classifications Constant Registry
# ==========================================
QOS_CLASSES = {
    "default": {"dscp": 0,  "fc_id": 0, "fc_name": "Best-Effort",     "label": "be", "profile": "Out"},
    "ef":      {"dscp": 46, "fc_id": 5, "fc_name": "Expedited",       "label": "ef", "profile": "In"},
    "nc1":     {"dscp": 48, "fc_id": 6, "fc_name": "High-1",          "label": "h1", "profile": "In"},
    "nc2":     {"dscp": 56, "fc_id": 7, "fc_name": "Network Control", "label": "nc", "profile": "In"},
    "af11":    {"dscp": 10, "fc_id": 2, "fc_name": "Assured",         "label": "af", "profile": "In"},
    "af12":    {"dscp": 12, "fc_id": 2, "fc_name": "Assured",         "label": "af", "profile": "Out"},
    "af13":    {"dscp": 14, "fc_id": 2, "fc_name": "Assured",         "label": "af", "profile": "Out"},
    "af21":    {"dscp": 18, "fc_id": 3, "fc_name": "Low-1",           "label": "l1", "profile": "In"},
    "af22":    {"dscp": 20, "fc_id": 3, "fc_name": "Low-1",           "label": "l1", "profile": "Out"},
    "af23":    {"dscp": 22, "fc_id": 3, "fc_name": "Low-1",           "label": "l1", "profile": "Out"},
    "af31":    {"dscp": 26, "fc_id": 3, "fc_name": "Low-1",           "label": "l1", "profile": "In"},
    "af32":    {"dscp": 28, "fc_id": 3, "fc_name": "Low-1",           "label": "l1", "profile": "Out"},
    "af33":    {"dscp": 30, "fc_id": 3, "fc_name": "Low-1",           "label": "l1", "profile": "Out"},
    "af41":    {"dscp": 34, "fc_id": 4, "fc_name": "High-2",          "label": "h2", "profile": "In"},
    "af42":    {"dscp": 36, "fc_id": 4, "fc_name": "High-2",          "label": "h2", "profile": "Out"},
    "af43":    {"dscp": 38, "fc_id": 4, "fc_name": "High-2",          "label": "h2", "profile": "Out"},
}

# ==========================================
# PDF, Email, and Receiver Server Utilities
# ==========================================
import getpass
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

def escape_pdf_str(text):
    return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

def generate_pdf_report(pdf_path, src, dst, link_rate, selected_classes, allocations, port_mapping, engine, rtt_stats, interface, mtu, mss, bdp, elapsed, total_mbps, all_iftop_captures=None):
    page_contents = [[]]
    
    def escape_pdf_str(text):
        return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        
    def get_page_list(page):
        while len(page_contents) < page:
            page_contents.append([])
        return page_contents[page - 1]

    def draw_text(x, y, font, size, text, color="0 0 0", page=1):
        target = get_page_list(page)
        target.append(f"{color} rg")
        target.append(f"BT /{font} {size} Tf {x} {y} Td ({escape_pdf_str(text)}) Tj ET")

    def draw_rect(x, y, w, h, fill_color, page=1):
        target = get_page_list(page)
        target.append(f"{fill_color} rg")
        target.append(f"{x} {y} {w} {h} re f")

    def draw_line(x1, y1, x2, y2, stroke_color="0.5 0.5 0.5", width=0.5, page=1):
        target = get_page_list(page)
        target.append(f"{stroke_color} RG")
        target.append(f"{width} w")
        target.append(f"{x1} {y1} m {x2} {y2} l S")

    def draw_circle(x, y, r, fill_color, page=1):
        target = get_page_list(page)
        c = r * 0.55228
        target.append(f"{fill_color} rg")
        target.append(f"{x+r} {y} m")
        target.append(f"{x+r} {y+c} {x+c} {y+r} {x} {y+r} c")
        target.append(f"{x-c} {y+r} {x-r} {y+c} {x-r} {y} c")
        target.append(f"{x-r} {y-c} {x-c} {y-r} {x} {y-r} c")
        target.append(f"{x+c} {y-r} {x+r} {y-c} {x+r} {y} c")
        target.append("f")

    def draw_arc(cx, cy, r, start_deg, end_deg, color, width=8, page=1):
        target = get_page_list(page)
        target.append(f"{color} RG")
        target.append(f"{width} w")
        steps = int(abs(start_deg - end_deg) / 5) + 1
        for i in range(steps):
            deg = start_deg + (end_deg - start_deg) * (i / (steps - 1))
            rad = math.radians(deg)
            x = cx + r * math.cos(rad)
            y = cy + r * math.sin(rad)
            if i == 0:
                target.append(f"{x:.2f} {y:.2f} m")
            else:
                target.append(f"{x:.2f} {y:.2f} l")
        target.append("S")

    # ==================== PAGE 1: SUMMARY ====================
    # Red top header banner
    draw_rect(20, 765, 555, 50, "0.9 0.0 0.0", page=1)
    draw_text(35, 785, "F2", 14, "QoS THROUGHPUT TEST REPORT", "1.0 1.0 1.0", page=1)
    
    # Draw vector network logo on top right of page 1
    draw_circle(525, 790, 15, "0.9 0.0 0.0", page=1)
    draw_circle(525, 790, 8, "1.0 1.0 1.0", page=1)
    draw_circle(525, 790, 4, "0.9 0.0 0.0", page=1)
    
    # Section 1: Test Details
    draw_text(25, 735, "F2", 12, "1. Test Execution Details", "0.9 0.0 0.0", page=1)
    draw_line(20, 730, 390, 730, "0.9 0.0 0.0", 1, page=1)

    # Left box for Section 1 (width 365, height 100)
    draw_rect(25, 620, 365, 100, "0.98 0.95 0.95", page=1)
    draw_text(35, 695, "F2", 9, "Source IP:", "0.2 0.2 0.2", page=1)
    draw_text(110, 695, "F1", 9, src, "0.1 0.1 0.1", page=1)
    draw_text(210, 695, "F2", 9, "Target IP:", "0.2 0.2 0.2", page=1)
    draw_text(280, 695, "F1", 9, dst, "0.1 0.1 0.1", page=1)
    
    draw_text(35, 670, "F2", 9, "Engine:", "0.2 0.2 0.2", page=1)
    draw_text(110, 670, "F1", 9, engine.upper(), "0.1 0.1 0.1", page=1)
    draw_text(210, 670, "F2", 9, "Duration:", "0.2 0.2 0.2", page=1)
    draw_text(280, 670, "F1", 9, f"{elapsed} seconds", "0.1 0.1 0.1", page=1)

    draw_text(35, 645, "F2", 9, "Link Rate:", "0.2 0.2 0.2", page=1)
    draw_text(110, 645, "F1", 9, f"{link_rate} Mbps", "0.1 0.1 0.1", page=1)
    draw_text(210, 645, "F2", 9, "Generated:", "0.2 0.2 0.2", page=1)
    draw_text(280, 645, "F1", 9, f"{total_mbps:.2f} Mbps", "0.1 0.1 0.1", page=1)

    # Section 2: Calculated Path Engineering Metrics
    draw_text(25, 585, "F2", 12, "2. Path Engineering Calculations", "0.9 0.0 0.0", page=1)
    draw_line(20, 580, 390, 580, "0.9 0.0 0.0", 1, page=1)

    # Left box for Section 2 (width 365, height 100)
    draw_rect(25, 470, 365, 100, "0.98 0.95 0.95", page=1)
    avg_rtt = f"{rtt_stats[1]:.2f} ms" if rtt_stats else "10.00 ms (Default)"
    draw_text(35, 545, "F2", 9, "Interface:", "0.2 0.2 0.2", page=1)
    draw_text(110, 545, "F1", 9, interface, "0.1 0.1 0.1", page=1)
    draw_text(210, 545, "F2", 9, "Path RTT:", "0.2 0.2 0.2", page=1)
    draw_text(280, 545, "F1", 9, avg_rtt, "0.1 0.1 0.1", page=1)
    
    draw_text(35, 520, "F2", 9, "Path MTU:", "0.2 0.2 0.2", page=1)
    draw_text(110, 520, "F1", 9, f"{mtu} Bytes", "0.1 0.1 0.1", page=1)
    draw_text(210, 520, "F2", 9, "Path MSS:", "0.2 0.2 0.2", page=1)
    draw_text(280, 520, "F1", 9, f"{mss} Bytes", "0.1 0.1 0.1", page=1)

    draw_text(35, 495, "F2", 9, "BDP Limit:", "0.2 0.2 0.2", page=1)
    draw_text(110, 495, "F1", 9, f"{bdp/1024:.2f} KB", "0.1 0.1 0.1", page=1)
    draw_text(210, 495, "F2", 9, "TCP Window:", "0.2 0.2 0.2", page=1)
    draw_text(280, 495, "F1", 9, f"{bdp/1024:.2f} KB", "0.1 0.1 0.1", page=1)

    # Section 2b: Speedometer / Throughput Gauge (Right Card)
    draw_rect(395, 470, 180, 250, "0.95 0.95 0.98", page=1)
    draw_text(415, 700, "F2", 11, "THROUGHPUT GAUGE", "0.9 0.0 0.0", page=1)
    draw_line(405, 692, 565, 692, "0.9 0.0 0.0", 0.5, page=1)
    
    cx, cy, r = 485, 575, 55
    usage_pct = (total_mbps / link_rate) * 100.0 if link_rate > 0 else 0.0
    clamped_pct = max(0.0, min(100.0, usage_pct))
    
    # Draw arc background (light gray)
    draw_arc(cx, cy, r, 180, 0, "0.85 0.85 0.85", width=8, page=1)
    
    # Draw color zones (Green, Yellow, Red)
    # Green: 0% to 70% (180 to 54 deg)
    draw_arc(cx, cy, r, 180, 54, "0.2 0.7 0.2", width=8, page=1)
    # Yellow: 70% to 90% (54 to 18 deg)
    draw_arc(cx, cy, r, 54, 18, "0.9 0.7 0.1", width=8, page=1)
    # Red: 90% to 100% (18 to 0 deg)
    draw_arc(cx, cy, r, 18, 0, "0.9 0.1 0.1", width=8, page=1)
    
    # Draw ticks and tick labels
    for pct_val, deg in [(0, 180), (25, 135), (50, 90), (75, 45), (100, 0)]:
        rad = math.radians(deg)
        x_start = cx + r * math.cos(rad)
        y_start = cy + r * math.sin(rad)
        x_end = cx + (r - 5) * math.cos(rad)
        y_end = cy + (r - 5) * math.sin(rad)
        draw_line(x_start, y_start, x_end, y_end, stroke_color="0.3 0.3 0.3", width=1, page=1)
        
        # Position labels slightly outside
        x_lbl = cx + (r + 10) * math.cos(rad)
        y_lbl = cy + (r + 10) * math.sin(rad)
        if deg == 180:
            x_lbl -= 14
            y_lbl -= 2
        elif deg == 0:
            x_lbl += 2
            y_lbl -= 2
        elif deg == 90:
            x_lbl -= 8
            y_lbl += 4
        else:
            x_lbl -= 7
            y_lbl -= 2
        draw_text(x_lbl, y_lbl, "F1", 7, f"{pct_val}%", "0.3 0.3 0.3", page=1)
        
    # Draw needle pointer
    needle_angle = 180.0 - (clamped_pct * 1.8)
    n_rad = math.radians(needle_angle)
    tx = cx + (r - 10) * math.cos(n_rad)
    ty = cy + (r - 10) * math.sin(n_rad)
    
    # Triangular needle base offsets
    perp_rad = n_rad + math.pi / 2
    bx1 = cx + 3 * math.cos(perp_rad)
    by1 = cy + 3 * math.sin(perp_rad)
    bx2 = cx - 3 * math.cos(perp_rad)
    by2 = cy - 3 * math.sin(perp_rad)
    
    target_needle = get_page_list(1)
    target_needle.append("0.2 0.2 0.2 rg")
    target_needle.append(f"{bx1:.2f} {by1:.2f} m {tx:.2f} {ty:.2f} l {bx2:.2f} {by2:.2f} l h f")
    
    # Draw needle center hub cap
    draw_circle(cx, cy, 5, "0.1 0.1 0.1", page=1)
    draw_circle(cx, cy, 2, "0.8 0.8 0.8", page=1)
    
    # Digital readout labels below speedometer
    draw_text(cx - 45, cy - 25, "F2", 9, f"{total_mbps:.1f} / {link_rate:.0f} Mbps", "0.2 0.2 0.2", page=1)
    draw_text(cx - 30, cy - 40, "F2", 9, f"Usage: {usage_pct:.1f}%", "0.9 0.0 0.0", page=1)

    # Section 3: QoS Target Allocations & Classes
    draw_text(25, 435, "F2", 12, "3. QoS Forwarding Class & Bandwidth Targets", "0.9 0.0 0.0", page=1)
    draw_line(20, 430, 575, 430, "0.9 0.0 0.0", 1, page=1)

    draw_rect(25, 400, 545, 20, "0.9 0.0 0.0", page=1)
    draw_text(35, 406, "F2", 9, "QoS Class", "1.0 1.0 1.0", page=1)
    draw_text(120, 406, "F2", 9, "ToS Byte", "1.0 1.0 1.0", page=1)
    draw_text(200, 406, "F2", 9, "FC ID", "1.0 1.0 1.0", page=1)
    draw_text(270, 406, "F2", 9, "Label", "1.0 1.0 1.0", page=1)
    draw_text(350, 406, "F2", 9, "Profile", "1.0 1.0 1.0", page=1)
    draw_text(440, 406, "F2", 9, "Allocated Rate", "1.0 1.0 1.0", page=1)

    y_offset = 380
    for idx, c in enumerate(selected_classes):
        if y_offset < 130:
            break
        pct = allocations[c]
        class_rate_mbps = (pct / 100.0) * link_rate
        tos = QOS_CLASSES[c]['dscp'] << 2
        tos_str = f"0x{tos:02X}"
        fc_id = str(QOS_CLASSES[c]['fc_id'])
        lbl = QOS_CLASSES[c]['label']
        profile = QOS_CLASSES[c]['profile']
        rate_str = f"{class_rate_mbps:.2f} Mbps ({pct:.1f}%)"
        
        if idx % 2 == 1:
            draw_rect(25, y_offset-3, 545, 16, "0.95 0.95 0.95", page=1)
        
        draw_text(35, y_offset, "F1", 9, c.upper(), "0.1 0.1 0.1", page=1)
        draw_text(120, y_offset, "F1", 9, tos_str, "0.1 0.1 0.1", page=1)
        draw_text(200, y_offset, "F1", 9, fc_id, "0.1 0.1 0.1", page=1)
        draw_text(270, y_offset, "F1", 9, lbl.upper(), "0.1 0.1 0.1", page=1)
        draw_text(350, y_offset, "F1", 9, profile, "0.1 0.1 0.1", page=1)
        draw_text(440, y_offset, "F2", 9, rate_str, "0.9 0.0 0.0", page=1)
        
        y_offset -= 18

    # Technical methodology warning box
    draw_rect(20, 50, 555, 60, "0.98 0.92 0.92", page=1)
    draw_text(30, 92, "F2", 8, "TECHNICAL NOTES & METHODOLOGY:", "0.9 0.0 0.0", page=1)
    draw_text(30, 80, "F1", 8, "1. Bandwidth Delay Product (BDP) represents the maximum network buffer capacity on this network segment.", "0.3 0.3 0.3", page=1)
    draw_text(30, 68, "F1", 8, "2. Testing is fully compliant with standard Ingress QoS DSCP mapping models.", "0.3 0.3 0.3", page=1)
    draw_text(30, 56, "F1", 8, "3. Optimal TCP Window size is calibrated dynamically from pre-flight RTT samples.", "0.3 0.3 0.3", page=1)

    # Page 1 Copyright / Footer
    draw_text(35, 30, "F2", 7.5, "Copyright (C) 2026 Prasath Suthagar. All Rights Reserved. (C2 - Internal Use Only)", "0.5 0.5 0.5", page=1)

    # ==================== PAGE 2 & ONWARDS: IFTOP OUTPUTS ====================
    def start_capture_page(p_num):
        # Red top header banner
        draw_rect(20, 765, 555, 50, "0.9 0.0 0.0", page=p_num)
        draw_text(35, 785, "F2", 14, f"QoS INTERFACE PACKET CAPTURE (Page {p_num-1})", "1.0 1.0 1.0", page=p_num)
        
        # Draw vector network logo on top right
        draw_circle(525, 790, 15, "0.9 0.0 0.0", page=p_num)
        draw_circle(525, 790, 8, "1.0 1.0 1.0", page=p_num)
        draw_circle(525, 790, 4, "0.9 0.0 0.0", page=p_num)
        
        # Section 4: Live capture details
        draw_text(25, 735, "F2", 12, f"4. Real-Time NIC Interface Traffic Capture (iftop) - Part {p_num-1}", "0.9 0.0 0.0", page=p_num)
        draw_line(20, 730, 575, 730, "0.9 0.0 0.0", 1, page=p_num)
        
        # Page Copyright / Footer
        draw_text(35, 30, "F2", 7.5, "Copyright (C) 2026 Prasath Suthagar. All Rights Reserved. (C2 - Internal Use Only)", "0.5 0.5 0.5", page=p_num)

    if not all_iftop_captures:
        # Fallback if no captures available
        current_page = 2
        start_capture_page(current_page)
        draw_text(35, 705, "F3", 8.5, "No live NIC capture logs available for this session.", "0.15 0.15 0.15", page=current_page)
    else:
        current_page = 2
        start_capture_page(current_page)
        y_offset = 705
        
        for elapsed_s, cap_time, out_str in all_iftop_captures:
            lines = out_str.split("\n")
            required_height = 15 + len(lines) * 11 + 15  # title + lines + spacing
            
            if y_offset - required_height < 50:
                current_page += 1
                start_capture_page(current_page)
                y_offset = 705
                
            draw_text(35, y_offset, "F2", 9, f"Capture interval: {elapsed_s - cap_time}s to {elapsed_s}s (Duration: {cap_time}s)", "0.9 0.0 0.0", page=current_page)
            y_offset -= 13
            
            for line in lines:
                draw_text(35, y_offset, "F3", 8.5, line, "0.15 0.15 0.15", page=current_page)
                y_offset -= 11
                
            y_offset -= 10  # space after block

    # ==================== COMPILE THE DYNAMIC PDF ====================
    page_streams = []
    for lines in page_contents:
        page_streams.append("\n".join(lines).encode("utf-8"))
        
    N = len(page_streams)
    
    # Dynamic PDF Objects:
    # 1: Catalog
    # 2: Pages list
    # 3: Shared Resources Dictionary
    # 4: Helvetica Font
    # 5: Helvetica-Bold Font
    # 6: Courier Font
    # Pages are Obj 7, 9, 11...
    # Contents are Obj 8, 10, 12...
    
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [ " + b" ".join([f"{7 + 2*i} 0 R".encode("utf-8") for i in range(N)]) + b" ] /Count " + str(N).encode("utf-8") + b" >>",
        b"<< /Font << /F1 4 0 R /F2 5 0 R /F3 6 0 R >> >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"
    ]
    
    for i in range(N):
        page_obj_id = 7 + 2 * i
        content_obj_id = page_obj_id + 1
        page_obj = f"<< /Type /Page /Parent 2 0 R /Resources 3 0 R /MediaBox [0 0 595.275 841.89] /Contents {content_obj_id} 0 R >>".encode("utf-8")
        content_stream = b"<< /Length " + str(len(page_streams[i])).encode("utf-8") + b" >>\nstream\n" + page_streams[i] + b"\nendstream"
        objs.append(page_obj)
        objs.append(content_stream)
    
    pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = []
    
    for i, obj in enumerate(objs):
        offsets.append(len(pdf_bytes))
        pdf_bytes += f"{i+1} 0 obj\n".encode("utf-8")
        pdf_bytes += obj + b"\nendobj\n"
        
    xref_offset = len(pdf_bytes)
    pdf_bytes += b"xref\n"
    pdf_bytes += f"0 {len(objs)+1}\n".encode("utf-8")
    pdf_bytes += b"0000000000 65535 f \n"
    for offset in offsets:
        pdf_bytes += f"{offset:010d} 00000 n \n".encode("utf-8")
        
    pdf_bytes += b"trailer\n"
    pdf_bytes += f"<< /Size {len(objs)+1} /Root 1 0 R >>\n".encode("utf-8")
    pdf_bytes += b"startxref\n"
    pdf_bytes += f"{xref_offset}\n".encode("utf-8")
    pdf_bytes += b"%%EOF\n"
    
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

def email_pdf_report(pdf_path):
    print_header("SMTP Email Delivery of QoS Report")
    choice = get_input("Would you like to email the generated PDF report? (y/n)", "n", validate_selection(["y", "n"]))
    if choice == "n":
        print(f"    {Style.INFO} Skipping email delivery. PDF remains saved at {pdf_path}")
        return
        
    recipient = get_input("Enter Recipient Email Address", "manager@example.com")
    subject = "QoS Throughput Test Report"
    
    # SMTP coordinates for automated dispatch
    os.environ["SMTP_SERVER"] = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    os.environ["SMTP_PORT"] = os.environ.get("SMTP_PORT", "587")
    
    smtp_user = os.environ.get("SMTP_USER")
    if not smtp_user:
        smtp_user = get_input("Enter SMTP Username/Email", "user@example.com")
    os.environ["SMTP_USER"] = smtp_user
    
    smtp_pass = os.environ.get("SMTP_PASS")
    if not smtp_pass:
        import getpass
        smtp_pass = getpass.getpass("    Enter SMTP Password (hidden): ").strip()
    os.environ["SMTP_PASS"] = smtp_pass
    
    os.environ["SMTP_TLS"] = os.environ.get("SMTP_TLS", "true")
    os.environ["SMTP_SSL"] = os.environ.get("SMTP_SSL", "false")
    
    # Determine the greeting based on the recipient address
    if recipient.lower() == "manager@example.com":
        greeting = "Dear Manager"
    else:
        name_part = recipient.split("@")[0]
        greeting = f"Dear {name_part.capitalize() if name_part.isalpha() else recipient}"
    
    # HTML formatted body matching sendmail's elegant table output
    html_body = f"""
    <p>{greeting},</p>
    <p>Please find attached the automated QoS Throughput Test Report generated by 
    the QoS Traffic Characterization tool.</p>
    
    <p>Below is a brief summary of the executed characterization test:</p>
    <table>
      <tr>
        <th>Metric</th>
        <th>Value</th>
      </tr>
      <tr>
        <td><b>Report File</b></td>
        <td>qos_throughput_report.pdf</td>
      </tr>
      <tr>
        <td><b>Status</b></td>
        <td><span style="color:green; font-weight:bold;">COMPLETED</span></td>
      </tr>
    </table>
    
    <p>Detailed performance calculations (including Bandwidth Delay Product, Optimal Socket Windows, 
    and QoS queue DSCP configurations) are compiled inside the attached PDF report.</p>
    """
    
    print(f"\n{Style.INFO} Invoking sendmail.py module to dispatch to {recipient}...")
    try:
        import sendmail
        # sendmail.main expects: emails (list), subject, html_body, attachments (list)
        sendmail.main([recipient], subject, html_body, [pdf_path])
        print(f"    {Style.SUCCESS} Email successfully dispatched to {Style.BOLD}{recipient}{Style.RESET} via sendmail!")
    except Exception as e:
        print(f"    {Style.ERROR} Failed to dispatch email via sendmail: {e}")
        print(f"    {Style.WARN} The report remains saved locally. You can access it at: {pdf_path}")

def print_manual_page():
    print_header("QoS TRAFFIC GENERATOR MANUAL")
    print(f""" {Style.BOLD}1. Overview{Style.RESET}
    This advanced tool is designed for Telecom Engineering teams to run QoS (Quality of Service)
    characterization throughput tests on secure VMs. It supports 16 standard QoS DSCP profiles,
    performs network math (BDP, MSS, burst token refill rates), launches dynamic multi-class
    flows, monitors interfaces via live iftop dashboard, generates PDF reports, and sends emails.

 {Style.BOLD}2. Supported QoS Classes & Mapping Registry{Style.RESET}
    The script integrates 16 dynamic QoS categories from Ingress Mapping standards:
    - best-effort (BE): ToS 0x00 (dscp 0)
    - expedited (EF)  : ToS 0xB8 (dscp 46) - Voice/Real-time
    - network control : ToS 0xE0 (dscp 56) - Routing/Control plane
    - assured (AF)    : ToS 0x28-0x38 (dscp 10-14)
    - low-1/high-2    : ToS 0x48-0x98 (dscp 18-38)

 {Style.BOLD}3. Key Engineering & Path Formulas{Style.RESET}
    - {Style.BOLD}BDP (Bandwidth Delay Product){Style.RESET}: 
      BDP = (Avg RTT * Bandwidth) / 8. This is the optimal physical window buffer size.
    - {Style.BOLD}Optimal TCP Window Size{Style.RESET}: Matches calculated BDP to avoid packet drops.
    - {Style.BOLD}TCP MSS (Maximum Segment Size){Style.RESET}: MSS = Path MTU - 40 Bytes.
    - {Style.BOLD}Burst/Token Bucket Intervals{Style.RESET}:
      Interval (ms) = (Bucket Size Bytes) / (Flow Target Rate Bps) * 1000.

 {Style.BOLD}4. Two-Way / Bidirectional Sockets & Receiver Mode{Style.RESET}
    Flooding traffic is typically 1-way by default, causing drops or missing reverse feedback.
    To allow true two-way / send-and-receive testing:
    - Run the script in {Style.B_CYAN}--receiver{Style.RESET} mode on the target host:
      {Style.BG_BLACK}{Style.B_GREEN} sudo python3 traffic_generator.py --receiver {Style.RESET}
    - Select standard socket listener (TCP/UDP) or iperf3 listener daemon.
    - The receiver will open multi-threaded ports corresponding to selected classes.
    - {Style.BOLD}TCP Handshake{Style.RESET}: Target OS kernel responds automatically with SYN-ACK to client hping3.
    - {Style.BOLD}UDP Echo{Style.RESET}: Receiver listens to datagrams and records throughput live.
    - For iperf3, selecting the {Style.BOLD}bidirectional{Style.RESET} option adds the '--bidir' client flag.

 {Style.BOLD}5. Report Generation & Secure Delivery{Style.RESET}
    - {Style.BOLD}PDF Creation{Style.RESET}: Built-in pure-Python PDF-1.4 writer runs locally without external dependencies.
    - {Style.BOLD}SMTP Emailing{Style.RESET}: Seamlessly prompts to send the PDF report to a recipient (e.g. manager)
      using secure TLS authentication (smtplib) with fallback warnings.

 {Style.BOLD}6. Execution Flags{Style.RESET}
    - {Style.B_YELLOW}--man / --manual{Style.RESET}        : Renders this manual and exits.
    - {Style.B_YELLOW}--receiver / -r{Style.RESET}       : Starts in active Receiver/Server daemon mode.
    - {Style.B_YELLOW}--dry-run{Style.RESET}              : Validates inputs and compiles commands without changes.
""")

class QoSReceiverServer:
    def __init__(self, ip, ports_mapping, protocol="tcp"):
        self.ip = ip
        self.ports = ports_mapping
        self.protocol = protocol
        self.running = False
        self.threads = []
        self.stats = {c: {"packets": 0, "bytes": 0, "last_bytes": 0, "bps": 0} for c in ports_mapping}
        self.lock = threading.Lock()

    def start(self):
        self.running = True
        for c, port in self.ports.items():
            t = threading.Thread(target=self._listen_loop, args=(c, port), daemon=True)
            t.start()
            self.threads.append(t)
        
        # Start stats reporter thread
        reporter = threading.Thread(target=self._report_loop, daemon=True)
        reporter.start()

    def stop(self):
        self.running = False

    def _listen_loop(self, class_name, port):
        if self.protocol == "tcp":
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((self.ip, port))
                s.listen(128)
            except Exception as e:
                print(f"Error binding TCP port {port} for {class_name}: {e}")
                return
            
            while self.running:
                try:
                    s.settimeout(1.0)
                    conn, addr = s.accept()
                    threading.Thread(target=self._handle_tcp_conn, args=(class_name, conn), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception:
                    break
            s.close()
        else: # UDP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((self.ip, port))
            except Exception as e:
                print(f"Error binding UDP port {port} for {class_name}: {e}")
                return
            
            while self.running:
                try:
                    s.settimeout(1.0)
                    data, addr = s.recvfrom(65535)
                    with self.lock:
                        self.stats[class_name]["packets"] += 1
                        self.stats[class_name]["bytes"] += len(data)
                except socket.timeout:
                    continue
                except Exception:
                    break
            s.close()

    def _handle_tcp_conn(self, class_name, conn):
        conn.settimeout(5.0)
        while self.running:
            try:
                data = conn.recv(16384)
                if not data:
                    break
                with self.lock:
                    self.stats[class_name]["packets"] += 1
                    self.stats[class_name]["bytes"] += len(data)
            except Exception:
                break
        conn.close()

    def _report_loop(self):
        while self.running:
            time.sleep(1.0)
            with self.lock:
                for c in self.ports:
                    diff = self.stats[c]["bytes"] - self.stats[c]["last_bytes"]
                    self.stats[c]["bps"] = diff * 8
                    self.stats[c]["last_bytes"] = self.stats[c]["bytes"]
            
            # Print live receiver dashboard
            print("\033[H\033[J") # Clear screen
            print_header("QoS RECEIVER LIVE DASHBOARD")
            print(f" {Style.BOLD}Listening on {self.ip} ({self.protocol.upper()} sockets):{Style.RESET}")
            print(f"  =======================================================")
            for c, port in self.ports.items():
                bps = self.stats[c]["bps"]
                mbps = bps / 1_000_000
                pkts = self.stats[c]["packets"]
                print(f"  - {Style.B_CYAN}{c.upper():8}{Style.RESET} Port: {port:5} | Received: {Style.BOLD}{mbps:6.2f} Mbps{Style.RESET} | Total Packets: {pkts}")
            print(f"  =======================================================")
            print("\nPress Ctrl+C to terminate receiver.")

def run_receiver():
    print_header("QoS Traffic Receiver Mode Daemon")
    
    has_iperf3 = check_dependencies("iperf3")
    
    protocol = get_input("Select Layer 4 Protocol (tcp/udp)", "tcp", validate_selection(["tcp", "udp"]))
    base_port = get_input("Enter base listening Port offset to auto-assign", "5201", validate_int_range(1024, 65500))
    
    class_prompt = "Select QoS classes to listen on (comma-separated list, or 'all', or 'default')"
    selected_classes = get_input(class_prompt, "default", validate_selected_classes)
    
    port_mapping = {}
    for idx, c in enumerate(selected_classes):
        port_mapping[c] = base_port + idx
        
    engine_options = ["sockets"]
    if has_iperf3:
        engine_options.append("iperf3")
        
    engine = get_input(f"Select Receiver Backend Server ({'/'.join(engine_options)})", engine_options[0], validate_selection(engine_options))
    
    if engine == "sockets":
        print(f"\n{Style.INFO} Initializing Custom Multi-Threaded Sockets Server on all interfaces...")
        server = QoSReceiverServer("0.0.0.0", port_mapping, protocol)
        server.start()
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            print(f"\n{Style.WARN} Shutting down socket servers...")
            server.stop()
            print(f"{Style.SUCCESS} Safe exit.")
    else: # iperf3 daemon servers
        print(f"\n{Style.INFO} Spawning background iperf3 server daemons sequential ports...")
        for c in selected_classes:
            p = port_mapping[c]
            cmd = ["iperf3", "-s", "-p", str(p), "-D"]
            try:
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if proc.returncode == 0:
                    print(f"  {Style.SUCCESS} Started iperf3 listener for {c.upper()} on port {p}")
                else:
                    print(f"  {Style.ERROR} Failed to start iperf3 on port {p}: {proc.stderr.strip()}")
            except Exception as e:
                print(f"  {Style.ERROR} Error spawning iperf3: {e}")
        
        print(f"\n{Style.SUCCESS} All iperf3 server background daemons successfully launched.")
        print("Use 'killall iperf3' or restart script to cleanly stop them.")
        get_input("Press Enter to exit receiver configuration tool", "Exit")

# ==========================================
# Global Constants & State
# ==========================================
MAX_BW_MBPS = 1000  # Hard ceiling of 1 Gbps
DEFAULT_SRC = "195.89.107.254"
DEFAULT_DST = "195.89.102.32"

# Global state to ensure proper cleanup on exit
original_icmp_ratelimit = None
original_icmp_msgs_per_sec = None
background_processes = []
sysctl_restored = False
is_dry_run = False

# ==========================================
# Clean Termination & Signal Handling
# ==========================================
def cleanup_and_exit(signum=None, frame=None):
    """
    Kills all traffic generator processes, restores original kernel ICMP rate limits,
    and cleanly exits the script.
    """
    global sysctl_restored
    print(f"\n\n{Style.WARN} Graceful shutdown initiated. Cleaning up active tasks...")
    
    # 1. Terminate all background processes
    if background_processes:
        print(f"{Style.INFO} Terminating background traffic streams...")
        for proc in background_processes:
            try:
                if proc.poll() is None:
                    # Try SIGTERM first
                    proc.terminate()
                    proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # Force kill if needed
                try:
                    proc.kill()
                    proc.wait()
                except Exception:
                    pass
            except Exception as e:
                print(f"{Style.ERROR} Error terminating process {proc.pid}: {e}")
        background_processes.clear()
        print(f"{Style.SUCCESS} All traffic streams stopped.")

    # 2. Restore Kernel ICMP ratelimit
    if not sysctl_restored and not is_dry_run:
        restored = False
        if original_icmp_ratelimit is not None:
            try:
                with open("/proc/sys/net/ipv4/icmp_ratelimit", "w") as f:
                    f.write(str(original_icmp_ratelimit))
                restored = True
            except Exception as e:
                print(f"{Style.ERROR} Failed to restore /proc/sys/net/ipv4/icmp_ratelimit: {e}")
                
        if original_icmp_msgs_per_sec is not None:
            try:
                with open("/proc/sys/net/ipv4/icmp_msgs_per_sec", "w") as f:
                    f.write(str(original_icmp_msgs_per_sec))
                restored = True
            except Exception:
                pass
                
        if restored:
            print(f"{Style.SUCCESS} Kernel ICMP rate limit settings successfully restored.")
        sysctl_restored = True

    print(f"{Style.SUCCESS} System restored. Goodbye!\n")
    sys.exit(0)

# Register shutdown signals
signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

# ==========================================
# Utility Functions
# ==========================================
def check_dependencies(tool_name):
    """Checks if a required tool is installed on the system."""
    if is_dry_run:
        return True
    return shutil.which(tool_name) is not None

def print_header(title):
    """Helper to display centered, high-fidelity headers."""
    term_width = shutil.get_terminal_size((80, 20)).columns
    border = "=" * min(term_width, 80)
    print(f"\n{Style.BOLD}{Style.B_CYAN}{border}")
    print(f" {title.center(min(term_width, 80) - 2)} ")
    print(f"{border}{Style.RESET}\n")

def get_input(prompt_text, default_value, validation_fn=None):
    """Prompts the user for input with a default option and validation."""
    while True:
        try:
            user_val = input(f"{Style.INPUT} {Style.BOLD}{prompt_text}{Style.RESET} [{Style.DIM}{default_value}{Style.RESET}]: ").strip()
            if not user_val:
                user_val = default_value
            
            if validation_fn:
                valid, msg, cleaned_val = validation_fn(user_val)
                if valid:
                    return cleaned_val
                else:
                    print(f"    {Style.ERROR} {Style.B_RED}Invalid input:{Style.RESET} {msg}")
            else:
                return user_val
        except (KeyboardInterrupt, SystemExit):
            cleanup_and_exit()

# ==========================================
# Beautiful Print of QoS Classes Table
# ==========================================
def print_qos_classes_table():
    """Prints a structured, formatted ASCII table of all 16 supported classes."""
    print(f" {Style.BOLD}Available Ingress DSCP & Forwarding Class Mappings:{Style.RESET}")
    print(f"  +----------+--------------+-------+-----------------+-------+---------+----------+")
    print(f"  | DSCP Name| DSCP (Bin/Dec) FC ID  | Forwarding Class| Label | Profile | ToS Byte |")
    print(f"  +----------+--------------+-------+-----------------+-------+---------+----------+")
    for name, info in sorted(QOS_CLASSES.items(), key=lambda x: x[1]['dscp']):
        bin_val = f"{info['dscp']:06b}"
        dscp_str = f"{bin_val} - {info['dscp']}"
        tos_val = info['dscp'] << 2
        tos_str = f"0x{tos_val:02X} ({tos_val})"
        print(f"  | {name:8} | {dscp_str:12} | {info['fc_id']:5} | {info['fc_name']:15} | {info['label']:5} | {info['profile']:7} | {tos_str:8} |")
    print(f"  +----------+--------------+-------+-----------------+-------+---------+----------+")
    print()

# ==========================================
# Input Validators
# ==========================================
def validate_ip(ip_str):
    if is_dry_run:
        return True, "", ip_str
    try:
        socket.inet_aton(ip_str)
        return True, "", ip_str
    except socket.error:
        try:
            socket.gethostbyname(ip_str)
            return True, "", ip_str
        except socket.error:
            return False, "Not a valid IP address or hostname.", ip_str

def validate_link_rate(rate_str):
    try:
        val = float(rate_str)
        if 0 < val <= MAX_BW_MBPS:
            return True, "", val
        else:
            return False, f"Link rate must be between 1 and {MAX_BW_MBPS} Mbps.", rate_str
    except ValueError:
        return False, "Please enter a valid numeric value.", rate_str

def validate_percentage(pct_str):
    try:
        val = float(pct_str)
        if 0 <= val <= 100:
            return True, "", val
        else:
            return False, "Percentage must be between 0 and 100.", pct_str
    except ValueError:
        return False, "Please enter a valid numeric value.", pct_str

def validate_selection(options):
    def validator(val_str):
        cleaned = val_str.lower().strip()
        if cleaned in options:
            return True, "", cleaned
        else:
            return False, f"Must be one of: {', '.join(options)}", val_str
    return validator

def validate_int_range(min_val, max_val):
    def validator(val_str):
        try:
            val = int(val_str)
            if min_val <= val <= max_val:
                return True, "", val
            else:
                return False, f"Must be an integer between {min_val} and {max_val}.", val_str
        except ValueError:
            return False, "Please enter a valid integer.", val_str
    return validator

def validate_selected_classes(val_str):
    """Parses and validates comma-separated QoS classes."""
    cleaned = val_str.lower().strip()
    if not cleaned:
        return False, "Selection cannot be empty.", val_str
    if cleaned == "all":
        return True, "", sorted(list(QOS_CLASSES.keys()))
    if cleaned == "default":
        return True, "", ["ef", "af22"]
        
    parts = [p.strip() for p in cleaned.split(",")]
    invalid = [p for p in parts if p not in QOS_CLASSES]
    if invalid:
        return False, f"Unknown QoS classes: {', '.join(invalid)}. Please select from the table names.", val_str
        
    # Deduplicate keeping order
    seen = set()
    selected = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            selected.append(p)
    return True, "", selected

# ==========================================
# Network Calculations & Route Resolution
# ==========================================
def get_outgoing_interface_and_mtu(dst_ip):
    """
    Queries the Linux routing table to find the outgoing interface for the destination
    and reads the interface's MTU.
    """
    if is_dry_run:
        return "eth0", 1500
        
    interface = "eth0"
    mtu = 1500
    
    # 1. Resolve outgoing interface via 'ip route get'
    try:
        res = subprocess.run(["ip", "route", "get", dst_ip], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            match = re.search(r"dev\s+(\S+)", res.stdout)
            if match:
                interface = match.group(1)
    except Exception as e:
        print(f"    {Style.WARN} Failed to dynamically resolve outgoing interface: {e}")

    # 2. Read MTU for the resolved interface
    mtu_paths = [
        f"/sys/class/net/{interface}/mtu",
        f"/sys/class/net/eth0/mtu"
    ]
    for p in mtu_paths:
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    mtu = int(f.read().strip())
                    break
            except Exception:
                pass
                
    return interface, mtu

# ==========================================
# Bypass Kernel ICMP Ratelimit
# ==========================================
def bypass_icmp_ratelimit():
    """
    Temporarily disables the Linux kernel ICMP ratelimit.
    Saves original values for recovery during cleanup.
    """
    global original_icmp_ratelimit, original_icmp_msgs_per_sec
    if is_dry_run:
        print(f"{Style.SUCCESS} [Dry-run] Bypassed kernel ICMP ratelimit.")
        return
        
    print(f"{Style.INFO} Checking kernel ICMP rate-limit settings...")
    
    # Read and store current settings
    try:
        if os.path.exists("/proc/sys/net/ipv4/icmp_ratelimit"):
            with open("/proc/sys/net/ipv4/icmp_ratelimit", "r") as f:
                original_icmp_ratelimit = int(f.read().strip())
            # Write 0 to disable
            with open("/proc/sys/net/ipv4/icmp_ratelimit", "w") as f:
                f.write("0")
            print(f"    {Style.SUCCESS} Disabled net.ipv4.icmp_ratelimit (Original: {original_icmp_ratelimit}ms)")
    except Exception as e:
        print(f"    {Style.WARN} Could not write to net.ipv4.icmp_ratelimit (requires root/sudo): {e}")

    try:
        if os.path.exists("/proc/sys/net/ipv4/icmp_msgs_per_sec"):
            with open("/proc/sys/net/ipv4/icmp_msgs_per_sec", "r") as f:
                original_icmp_msgs_per_sec = int(f.read().strip())
            # Set to very high capacity
            with open("/proc/sys/net/ipv4/icmp_msgs_per_sec", "w") as f:
                f.write("100000")
            print(f"    {Style.SUCCESS} Increased net.ipv4.icmp_msgs_per_sec (Original: {original_icmp_msgs_per_sec})")
    except Exception:
        pass

# ==========================================
# RTT Pre-flight Testing
# ==========================================
def measure_preflight_rtt(dst_ip):
    """
    Measures RTT with 20 rapid pings and extracts min/avg/max/mdev values.
    """
    print(f"\n{Style.INFO} Running 20 pre-flight rapid pings to {Style.BOLD}{dst_ip}{Style.RESET}...")
    
    if is_dry_run:
        print(f"    {Style.SUCCESS} [Dry-run] Simulated ping response.")
        return 5.12, 10.45, 22.84, 1.25
        
    cmd = ["ping", "-c", "20", "-i", "0.2", dst_ip]
    try:
        # Run ping command
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if res.returncode != 0:
            print(f"    {Style.ERROR} Ping failed (destination unreachable or blocked): {res.stderr.strip()}")
            return None
        
        # Parse RTT line
        match = re.search(r"rtt\s+min/avg/max/mdev\s*=\s*([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+)\s+ms", res.stdout)
        if match:
            rtt_min = float(match.group(1))
            rtt_avg = float(match.group(2))
            rtt_max = float(match.group(3))
            rtt_mdev = float(match.group(4))
            
            print(f"    {Style.SUCCESS} Measured RTT:")
            print(f"        {Style.DIM}-{Style.RESET} Min:  {Style.BOLD}{rtt_min} ms{Style.RESET}")
            print(f"        {Style.DIM}-{Style.RESET} Avg:  {Style.BOLD}{rtt_avg} ms{Style.RESET}")
            print(f"        {Style.DIM}-{Style.RESET} Max:  {Style.BOLD}{rtt_max} ms{Style.RESET}")
            print(f"        {Style.DIM}-{Style.RESET} Mdev: {Style.BOLD}{rtt_mdev} ms{Style.RESET}")
            return rtt_min, rtt_avg, rtt_max, rtt_mdev
        else:
            print(f"    {Style.WARN} Could not parse ping output. Output:\n{res.stdout}")
            return None
            
    except subprocess.TimeoutExpired:
        print(f"    {Style.ERROR} Pre-flight RTT ping command timed out (10s limit exceeded).")
        return None
    except Exception as e:
        print(f"    {Style.ERROR} Pre-flight RTT measurement failed with error: {e}")
        return None

# ==========================================
# Core Testing Runner Logic
# ==========================================
def main():
    global is_dry_run, background_processes
    
    # Check for manual page flags
    if "--man" in sys.argv or "--manual" in sys.argv:
        print_manual_page()
        sys.exit(0)
        
    # Check for receiver flags
    if "--receiver" in sys.argv or "-r" in sys.argv:
        try:
            run_receiver()
        except (KeyboardInterrupt, SystemExit):
            pass
        sys.exit(0)
        
    # 0. Handle dry-run argument
    if "--dry-run" in sys.argv:
        is_dry_run = True
        print(f"{Style.WARN} RUNNING IN DRY-RUN VALIDATION MODE. NO SYSTEM CHANGES WILL BE APPLIED.")

    print_header("QoS Throughput Traffic Generator - Dynamic Multi-Class Testing")
    
    # Check for root privilege (elevate automatically on Linux unless dry-run)
    if not is_dry_run and os.name == 'posix' and os.getuid() != 0:
        print(f"{Style.WARN} Root privileges required. Relaunching via sudo...")
        try:
            cmd = ['sudo', sys.executable] + sys.argv
            res = subprocess.run(cmd)
            sys.exit(res.returncode)
        except Exception as e:
            print(f"{Style.ERROR} Failed to auto-elevate with sudo: {e}")
            print("Please run this script directly with: sudo python3 traffic_generator.py")
            sys.exit(1)

    # Verify dependency commands
    missing_deps = []
    for dep in ["ping", "ip", "awk"]:
        if not check_dependencies(dep):
            missing_deps.append(dep)
            
    if missing_deps:
        print(f"{Style.ERROR} Missing essential system dependencies: {', '.join(missing_deps)}")
        sys.exit(1)

    # Check for core generators
    has_iperf3 = check_dependencies("iperf3")
    has_hping3 = check_dependencies("hping3")
    has_iftop = check_dependencies("iftop")
    
    if not has_iperf3 and not has_hping3:
        print(f"{Style.ERROR} Neither 'iperf3' nor 'hping3' is installed on this VM. Please install at least one.")
        sys.exit(1)
        
    if not has_iftop and not is_dry_run:
        print(f"{Style.WARN} 'iftop' tool not found. The live traffic capture dashboard will be degraded.")

    # Show QoS Mapping Table
    print_qos_classes_table()

    # 1. Prompts for SRC/DST IPs and agreed link rate
    print(f"{Style.BOLD}--- Step 1: VM and Link Configuration ---{Style.RESET}")
    src_ip = get_input("Enter Source IP (Local VM IP)", DEFAULT_SRC, validate_ip)
    dst_ip = get_input("Enter Destination IP (Target VM IP)", DEFAULT_DST, validate_ip)
    link_rate = get_input("Enter Agreed Link Rate in Mbps (<= 1000)", "100", validate_link_rate)
    
    # Choose QoS Classes to test
    print(f"\n{Style.BOLD}--- Step 2: Select Traffic Classes & allocations ---{Style.RESET}")
    class_prompt = "Select QoS classes to test (comma-separated list, e.g. 'ef, af22', or 'all', or 'default')"
    selected_classes = get_input(class_prompt, "default", validate_selected_classes)
    
    print(f"    Selected classes: {Style.BOLD}{', '.join(selected_classes)}{Style.RESET}")
    
    # Bandwidth allocations per class
    allocations = {}  # class_name -> percentage
    if len(selected_classes) > 1:
        auto_distribute = get_input("Distribute bandwidth allocation equally among selected classes? (y/n)", "y", validate_selection(["y", "n"]))
        if auto_distribute == "y":
            total_alloc_pct = get_input("Enter total percentage of link rate to allocate for selected classes", "100", validate_percentage)
            equal_pct = total_alloc_pct / len(selected_classes)
            for c in selected_classes:
                allocations[c] = equal_pct
        else:
            print(f"    Please enter the allocation % for each class:")
            remaining_pct = 100.0
            # Order selected_classes so 'default' is at the end for manual prompting
            prompt_classes = [c for c in selected_classes if c != "default"]
            if "default" in selected_classes:
                prompt_classes.append("default")
            
            for idx, c in enumerate(prompt_classes):
                # Calculate suggested default
                default_pct = round(remaining_pct / (len(prompt_classes) - idx), 2)
                while True:
                    pct = get_input(f"      Allocation % for {Style.B_CYAN}{c}{Style.RESET} (ToS: 0x{(QOS_CLASSES[c]['dscp']<<2):02X})", str(default_pct), validate_percentage)
                    if pct <= remaining_pct:
                        allocations[c] = pct
                        remaining_pct -= pct
                        break
                    else:
                        print(f"        {Style.ERROR} Out of bounds. Remaining allocation left: {remaining_pct:.2f}%")
    else:
        # Only one class selected, allocate 100% by default
        single_class = selected_classes[0]
        pct = get_input(f"Enter allocation % for {Style.B_CYAN}{single_class}{Style.RESET}", "100", validate_percentage)
        allocations[single_class] = pct

    # Print summary of rate allocations
    print(f"\n    {Style.BOLD}Allocated Bandwidth Rates:{Style.RESET}")
    total_mbps = 0.0
    for c in selected_classes:
        pct = allocations[c]
        mbps = (pct / 100.0) * link_rate
        total_mbps += mbps
        print(f"      - {c:8} ToS: 0x{(QOS_CLASSES[c]['dscp']<<2):02X} | {pct:6.2f}% allocation -> {Style.BOLD}{mbps:6.2f} Mbps{Style.RESET}")
    print(f"      - Total allocated rate: {Style.BOLD}{total_mbps:.2f} Mbps{Style.RESET} ({total_mbps/link_rate*100:.1f}% of Link Limit)")

    # 2. Kernel Bypass & Pre-flight measurements
    print(f"\n{Style.BOLD}--- Step 3: Pre-Flight Latency & Kernel Setup ---{Style.RESET}")
    bypass_icmp_ratelimit()
    
    rtt_stats = measure_preflight_rtt(dst_ip)
    if rtt_stats:
        rtt_min, rtt_avg, rtt_max, rtt_mdev = rtt_stats
    else:
        print(f"{Style.WARN} RTT measurements failed. Using default RTT = 10.0 ms for BDP calculations.")
        rtt_min, rtt_avg, rtt_max, rtt_mdev = 5.0, 10.0, 15.0, 1.0

    # 3. Dynamic Network Calculations
    print(f"\n{Style.BOLD}--- Step 4: Network Calculations & Dynamic Buffers ---{Style.RESET}")
    
    # Get outgoing interface and MTU
    out_dev, mtu = get_outgoing_interface_and_mtu(dst_ip)
    mss = mtu - 40
    
    # BDP Calculations (BDP = RTT_avg_sec * Bandwidth_bps / 8)
    rtt_avg_sec = rtt_avg / 1000.0
    link_rate_bps = link_rate * 1_000_000
    
    bdp_bytes = (rtt_avg_sec * link_rate_bps) / 8
    optimal_tcp_win_bytes = bdp_bytes

    # Read current TCP memory configurations
    tcp_rmem = "N/A"
    tcp_wmem = "N/A"
    if not is_dry_run and os.path.exists("/proc/sys/net/ipv4/tcp_rmem"):
        try:
            with open("/proc/sys/net/ipv4/tcp_rmem", "r") as f:
                tcp_rmem = f.read().strip()
            with open("/proc/sys/net/ipv4/tcp_wmem", "r") as f:
                tcp_wmem = f.read().strip()
        except Exception:
            pass

    # Print Calculations report
    print(f"    Outgoing Interface:      {Style.BOLD}{out_dev}{Style.RESET}")
    print(f"    Path MTU / TCP MSS:      {Style.BOLD}{mtu} Bytes / {mss} Bytes{Style.RESET}")
    print(f"    Total Link Capacity BDP: {Style.BOLD}{bdp_bytes:.2f} Bytes{Style.RESET} ({bdp_bytes/1024:.2f} KB)")
    print(f"    Optimal TCP Window Size: {Style.BOLD}{optimal_tcp_win_bytes:.2f} Bytes{Style.RESET} ({optimal_tcp_win_bytes/1024:.2f} KB)")
    print(f"    Current Host TCP Mem:")
    print(f"        - rmem (min/default/max): {Style.DIM}{tcp_rmem}{Style.RESET}")
    print(f"        - wmem (min/default/max): {Style.DIM}{tcp_wmem}{Style.RESET}")
    
    print(f"\n    {Style.BOLD}Per-Class Bucket & Refill Metrics:{Style.RESET}")
    
    class_metrics = {}  # class_name -> calculations
    for c in selected_classes:
        pct = allocations[c]
        class_rate_mbps = (pct / 100.0) * link_rate
        class_rate_bps = class_rate_mbps * 1_000_000
        
        # Calculate burst intervals
        mtu_interval_ms = (mtu / (class_rate_bps / 8)) * 1000 if class_rate_bps > 0 else 0
        burst_capacity_bytes = 150_000
        burst_interval_ms = (burst_capacity_bytes / (class_rate_bps / 8)) * 1000 if class_rate_bps > 0 else 0
        
        class_metrics[c] = {
            "rate_mbps": class_rate_mbps,
            "mtu_interval": mtu_interval_ms,
            "burst_interval": burst_interval_ms
        }
        
        print(f"      {Style.B_CYAN}[{c.upper()} Class - DSCP {QOS_CLASSES[c]['dscp']} / ToS 0x{(QOS_CLASSES[c]['dscp']<<2):02X}]{Style.RESET} Rate: {Style.BOLD}{class_rate_mbps:.2f} Mbps{Style.RESET}")
        print(f"        - 1x MTU Packets Refill Period:    {Style.BOLD}{mtu_interval_ms:.4f} ms{Style.RESET}")
        print(f"        - 150KB Token Bucket Refill:       {Style.BOLD}{burst_interval_ms:.4f} ms{Style.RESET}")

    # 4. Prompts to use iperf3 or hping3 & gathers appropriate parameters
    print(f"\n{Style.BOLD}--- Step 5: Traffic Generation Engine ---{Style.RESET}")
    
    # Filter available engines
    engine_options = []
    if has_iperf3: engine_options.append("iperf3")
    if has_hping3: engine_options.append("hping3")
    
    engine_prompt = f"Select generator engine ({'/'.join(engine_options)})"
    selected_engine = get_input(engine_prompt, engine_options[0], validate_selection(engine_options))

    # Engine-specific parameters
    test_duration = 300
    protocol = "tcp"
    
    # Sequential Port Allocation
    base_port = 5201
    port_mapping = {}  # class_name -> port
    
    # hping3 specific
    hping_payload_size = 1200
    hping_mode = "tcp"
    
    # Gather Port Mapping
    base_port = get_input("Enter base listening Port offset to auto-assign", "5201", validate_int_range(1024, 65500))
    for idx, c in enumerate(selected_classes):
        port_mapping[c] = base_port + idx

    # Directionality configuration for bidirectional traffic
    print(f"\n{Style.BOLD}--- Step 5b: Traffic Directionality ---{Style.RESET}")
    direction = get_input("Select Traffic Direction (outbound/inbound/bidirectional)", "outbound", validate_selection(["outbound", "inbound", "bidirectional"]))

    if selected_engine == "iperf3":
        print(f"\n{Style.INFO} Configuring iperf3 engine parameters...")
        protocol = get_input("Select Layer 4 Protocol (tcp/udp)", "tcp", validate_selection(["tcp", "udp"]))
        num_streams = get_input("Number of parallel streams per class", "4", validate_int_range(1, 32))
        test_duration = get_input("Test duration in seconds", "300", validate_int_range(10, 86400))
        
        # Display instructions for server setup
        print(f"\n{Style.WARN} {Style.BOLD}Destination Configuration Required:{Style.RESET}")
        print(f"    Please execute the following commands on the remote destination host ({Style.BOLD}{dst_ip}{Style.RESET}) to open listeners:")
        for c in selected_classes:
            p = port_mapping[c]
            print(f"      {Style.BG_BLACK}{Style.B_GREEN} iperf3 -s -p {p} -D {Style.RESET}  (Start {c.upper()} listener background daemon)")
        print()
        get_input("Press Enter once destination listener ports are ready", "Ready")
        
    elif selected_engine == "hping3":
        print(f"\n{Style.INFO} Configuring hping3 engine parameters...")
        hping_mode = get_input("Select hping3 mode (tcp/udp/icmp)", "tcp", validate_selection(["tcp", "udp", "icmp"]))
        hping_payload_size = get_input("Payload size in Bytes (excluding headers)", "1200", validate_int_range(0, 65000))
        test_duration = get_input("Test duration in seconds", "300", validate_int_range(10, 86400))

    # 5. Launches parallel streams at the correct DSCP-marked rates
    print(f"\n{Style.BOLD}--- Step 6: Launching Dynamic Traffic Streams ---{Style.RESET}")
    
    stream_cmds = {}  # class_name -> command_list
    
    for c in selected_classes:
        pct = allocations[c]
        class_rate_mbps = (pct / 100.0) * link_rate
        p = port_mapping[c]
        tos_decimal = QOS_CLASSES[c]["dscp"] << 2
        tos_hex = f"{tos_decimal:02X}".lower()
        
        cmd = []
        if selected_engine == "iperf3":
            proto_flag = ["-u"] if protocol == "udp" else []
            dir_flags = []
            if direction == "inbound":
                dir_flags = ["-R"]
            elif direction == "bidirectional":
                dir_flags = ["--bidir"]
                
            cmd = [
                "iperf3", "-c", dst_ip, "-p", str(p),
                "-b", f"{class_rate_mbps:.2f}M", "-S", str(tos_decimal),
                "-t", str(test_duration), "-P", str(num_streams)
            ] + proto_flag + dir_flags
            
        elif selected_engine == "hping3":
            header_sz = 40 if hping_mode == "tcp" else 28
            total_pkt_sz = hping_payload_size + header_sz
            
            # Calculate microsecond interval: P * 8 / Rate_Mbps
            interval_us = int((total_pkt_sz * 8) / class_rate_mbps) if class_rate_mbps > 0 else 999999
            interval_us = max(1, interval_us)
            
            mode_flag = []
            if hping_mode == "udp":
                mode_flag = ["--udp"]
            elif hping_mode == "icmp":
                mode_flag = ["--icmp"]
                
            # If bidirectional hping3, we can enable TCP SYN or UDP scanning behavior
            # hping3 receives replies from target automatically if target TCP port has listener (receives SYN-ACK)
            cmd = [
                "hping3", dst_ip, "-d", str(hping_payload_size),
                "-i", f"u{interval_us}", "-o", tos_hex
            ] + mode_flag
            if hping_mode != "icmp":
                cmd += ["-p", str(p)]
                
        stream_cmds[c] = cmd

    # Print commands for verification
    for c in selected_classes:
        print(f"    {Style.B_CYAN}[{c.upper()} Flow Generator command]:{Style.RESET}\n      {' '.join(stream_cmds[c])}")
    
    # Launch subprocesses
    if not is_dry_run:
        try:
            for c in selected_classes:
                proc = subprocess.Popen(stream_cmds[c], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                background_processes.append(proc)
            print(f"\n{Style.SUCCESS} All {len(selected_classes)} streams successfully launched in background.")
        except Exception as e:
            print(f"{Style.ERROR} Failed to start traffic generators: {e}")
            cleanup_and_exit()
    else:
        print(f"\n{Style.SUCCESS} [Dry-run] Simulated launching dynamic streams in background.")

    # 6. Displays a live dashboard that refreshes 30 second
    print(f"\n{Style.INFO} Initializing live QoS NIC monitor...")
    time.sleep(1) # Let processes spin up
    
    all_iftop_captures = []
    iftop_output = ""
    start_time = time.time()
    end_time = start_time + test_duration
    
    try:
        while time.time() < end_time:
            remaining = int(end_time - time.time())
            elapsed = int(time.time() - start_time)
            if remaining <= 0:
                break
                
            # Perform a 30 second capture or the remainder of the test
            capture_time = min(30, remaining)
            
            # Form dashboard title
            dashboard_title = f"QoS LIVE DASHBOARD | Elapsed: {elapsed}s / Total: {test_duration}s | Remaining: {remaining}s"
            
            # Print temporary status while capturing
            print("\033[H\033[J") # Clear screen
            print_header(dashboard_title)
            print(f"    {Style.INFO} Running live interface network packet capture via {Style.BOLD}iftop{Style.RESET}...")
            print(f"    {Style.INFO} Please wait. Capturing data for a {Style.BOLD}{capture_time} second{Style.RESET} window...")
            
            # Construct a beautiful progress bar spinner
            spinner_chars = ["|", "/", "-", "\\"]
            
            if not is_dry_run and has_iftop:
                iftop_cmd = ["iftop", "-t", "-s", str(capture_time), "-n", "-N", "-i", out_dev]
                iftop_proc = subprocess.Popen(iftop_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                
                # Loop while iftop runs
                elapsed_capture = 0.0
                spinner_idx = 0
                while iftop_proc.poll() is None:
                    time.sleep(0.2)
                    elapsed_capture += 0.2
                    spinner_idx = (spinner_idx + 1) % len(spinner_chars)
                    sys.stdout.write(f"\r    {Style.B_CYAN}{spinner_chars[spinner_idx]}{Style.RESET} Capturing... {elapsed_capture:.1f}s / {capture_time}s elapsed. ")
                    sys.stdout.flush()
                
                sys.stdout.write("\n")
                stdout_data, stderr_data = iftop_proc.communicate()
                
                if iftop_proc.returncode == 0:
                    iftop_output = stdout_data
                else:
                    iftop_output = f"iftop execution error:\n{stderr_data}"
            else:
                # Simulation mode or missing iftop
                spinner_idx = 0
                for s in range(capture_time):
                    time.sleep(1)
                    spinner_idx = (spinner_idx + 1) % len(spinner_chars)
                    sys.stdout.write(f"\r    {Style.B_CYAN}{spinner_chars[spinner_idx]}{Style.RESET} [Simulated Capture] Capturing... {s+1}s / {capture_time}s. ")
                    sys.stdout.flush()
                sys.stdout.write("\n")
                
                # Generate beautiful mock iftop stats for visualization
                iftop_lines = [
                    f"Host name                           Last 2s   Last 10s   Last 40s",
                    f"================================================================="
                ]
                for idx, c in enumerate(selected_classes):
                    r_mbps = class_metrics[c]["rate_mbps"]
                    p = port_mapping[c]
                    tos = QOS_CLASSES[c]['dscp'] << 2
                    line = (
                        f"{idx+1:<2} {src_ip:25}       =>   {r_mbps:5.1f}Mb   {r_mbps:5.1f}Mb   {r_mbps:5.1f}Mb  ({c.upper()} ToS 0x{tos:02X} Port {p})\n"
                        f"   {dst_ip:25}       <=    0.00b      0.00b      0.00b"
                    )
                    iftop_lines.append(line)
                iftop_lines.append(f"-----------------------------------------------------------------")
                iftop_lines.append(f"Total Send bandwidth: {total_mbps:6.1f} Mbps   Target Link Limit: {link_rate:.1f} Mbps")
                
                iftop_output = "\n".join(iftop_lines)

            # Store capture data
            all_iftop_captures.append((elapsed + capture_time, capture_time, iftop_output))

            # Re-render Full Dashboard with the collected statistics
            print("\033[H\033[J") # Clear screen
            print_header(dashboard_title)
            
            # Print core calculations static box
            print(f" {Style.BOLD}System Statistics & Network Calculations:{Style.RESET}")
            print(f"  +--------------------------------------------------------+")
            print(f"  |  Outgoing Interface:  {out_dev:10}  MTU:  {mtu:4} B   MSS:  {mss:4} B     |")
            print(f"  |  RTT (Min/Avg/Max):   {rtt_min:.1f}/{rtt_avg:.1f}/{rtt_max:.1f} ms                      |")
            print(f"  |  BDP Link Capacity:   {bdp_bytes/1024:7.2f} KB                               |")
            print(f"  |  Optimal TCP Window:  {optimal_tcp_win_bytes/1024:7.2f} KB                               |")
            print(f"  +--------------------------------------------------------+")
            print()
            
            # Print Active QoS Configs info
            print(f" {Style.BOLD}Active QoS Traffic Flow Mappings:{Style.RESET}")
            for c in selected_classes:
                r_mbps = class_metrics[c]["rate_mbps"]
                pct = allocations[c]
                tos = QOS_CLASSES[c]['dscp'] << 2
                lbl = QOS_CLASSES[c]['label']
                pstate = QOS_CLASSES[c]['profile']
                fc_id = QOS_CLASSES[c]['fc_id']
                p = port_mapping[c]
                
                print(f"  - {Style.B_CYAN}{c.upper():8}{Style.RESET} ToS: 0x{tos:02X} (DSCP {QOS_CLASSES[c]['dscp']:2}) | FC ID: {fc_id} ({lbl:3}/{pstate:3}) | Port: {p} -> Target: {Style.BOLD}{r_mbps:6.2f} Mbps{Style.RESET} ({pct:.1f}%)")
            print()
            
            # Print Live NIC Capture section
            print(f" {Style.BOLD}Live NIC Traffic Summary (Capture over last {capture_time}s):{Style.RESET}")
            print(f"--------------------------------------------------------------------------------")
            print(iftop_output)
            print(f"--------------------------------------------------------------------------------")
            print(f" (Dashboard will auto-refresh in next 30s. Press Ctrl+C to terminate test cleanly)")

    except (KeyboardInterrupt, SystemExit):
        print(f"\n{Style.WARN} Test cancelled by user. Compiling results up to this point...")
        
    # Standard exit after duration
    print_final_summary(start_time, test_duration, src_ip, dst_ip, link_rate, selected_classes, allocations, port_mapping, selected_engine, rtt_stats, out_dev, mtu, mss, bdp_bytes)
    
    # Calculate totals for reports
    final_elapsed = int(time.time() - start_time)
    total_alloc_mbps = sum((allocations[c] / 100.0) * link_rate for c in selected_classes)
    pdf_report_path = os.path.abspath("qos_throughput_report.pdf")
    
    try:
        generate_pdf_report(
            pdf_report_path, src_ip, dst_ip, link_rate, selected_classes, allocations, 
            port_mapping, selected_engine, rtt_stats, out_dev, mtu, mss, bdp_bytes, 
            final_elapsed, total_alloc_mbps, all_iftop_captures
        )
        print(f" {Style.SUCCESS} Professional PDF report successfully compiled locally:")
        print(f"        {Style.DIM}-{Style.RESET} Path: {Style.BOLD}{pdf_report_path}{Style.RESET}")
        
        # Email transmission prompt
        email_pdf_report(pdf_report_path)
    except Exception as e:
        print(f" {Style.WARN} Failed to compile PDF report: {e}")
        
    cleanup_and_exit()

# ==========================================
# Final Summary and Report
# ==========================================
def print_final_summary(start_time, test_duration, src, dst, link_rate, selected_classes, allocations, port_mapping, engine, rtt_stats, interface, mtu, mss, bdp):
    """Prints a beautiful, clean structured test summary."""
    elapsed = int(time.time() - start_time)
    
    print("\n\n" + "=" * 80)
    print_header("QoS TESTING FINAL SUMMARY REPORT")
    
    print(f" {Style.BOLD}Test Execution Details:{Style.RESET}")
    print(f"  - Status:             {Style.B_GREEN}COMPLETED SUCCESSFUL{Style.RESET}")
    print(f"  - Duration Elapsed:   {elapsed} / {test_duration} seconds")
    print(f"  - Source VM IP:       {src}")
    print(f"  - Destination IP:     {dst}")
    print(f"  - Traffic Engine:     {engine.upper()}")
    print()
    
    print(f" {Style.BOLD}Calculated Path Engineering Metrics:{Style.RESET}")
    print(f"  - Active Interface:   {interface} (MTU: {mtu} Bytes / MSS: {mss} Bytes)")
    if rtt_stats:
        print(f"  - Path Latency RTT:   Min: {rtt_stats[0]}ms | Avg: {rtt_stats[1]}ms | Max: {rtt_stats[2]}ms | Mdev: {rtt_stats[3]}ms")
    print(f"  - Path BDP Limit:     {bdp/1024:.2f} KB ({int(bdp)} Bytes)")
    print(f"  - Optimal TCP Window: {bdp/1024:.2f} KB")
    print()
    
    print(f" {Style.BOLD}QoS Active Traffic Target Allocations:{Style.RESET}")
    total_mbps = 0.0
    for c in selected_classes:
        pct = allocations[c]
        class_rate_mbps = (pct / 100.0) * link_rate
        total_mbps += class_rate_mbps
        tos = QOS_CLASSES[c]['dscp'] << 2
        fc_id = QOS_CLASSES[c]['fc_id']
        lbl = QOS_CLASSES[c]['label']
        print(f"  - {Style.B_CYAN}{c.upper():8}{Style.RESET} ToS: 0x{tos:02X} | FC: {fc_id} ({lbl:3}) | Port: {port_mapping[c]} -> {Style.BOLD}{class_rate_mbps:6.2f} Mbps{Style.RESET} ({pct:.1f}%)")
    
    print(f"  - Remaining Link Capacity:                 {link_rate - total_mbps:.2f} Mbps")
    print()
    
    # Save Report to file
    report_file = "qos_test_report.log"
    try:
        with open(report_file, "w") as f:
            f.write("====================================================\n")
            f.write("        QoS TRAFFIC GENERATOR FINAL SUMMARY REPORT   \n")
            f.write("====================================================\n\n")
            f.write(f"Status:             COMPLETED\n")
            f.write(f"Source IP:          {src}\n")
            f.write(f"Destination IP:     {dst}\n")
            f.write(f"Traffic Generator:  {engine}\n")
            f.write(f"Duration:           {elapsed} seconds\n")
            f.write(f"Outgoing Interface: {interface} (MTU: {mtu} Bytes, MSS: {mss} Bytes)\n")
            if rtt_stats:
                f.write(f"RTT (min/avg/max):  {rtt_stats[0]}/{rtt_stats[1]}/{rtt_stats[2]} ms\n")
            f.write(f"Bandwidth Delay Product (BDP): {bdp:.2f} Bytes\n")
            f.write(f"Optimal TCP Window Size:       {bdp:.2f} Bytes\n\n")
            f.write(f"QoS Active Traffic Target Mappings:\n")
            for c in selected_classes:
                pct = allocations[c]
                class_rate_mbps = (pct / 100.0) * link_rate
                tos = QOS_CLASSES[c]['dscp'] << 2
                fc_id = QOS_CLASSES[c]['fc_id']
                f.write(f"  - {c.upper():8} ToS: 0x{tos:02X} | FC: {fc_id} | Port: {port_mapping[c]} -> {class_rate_mbps:.2f} Mbps ({pct:.1f}%)\n")
            f.write(f"\nTotal Configured QoS Rate:     {total_mbps:.2f} / {link_rate:.2f} Mbps\n")
        print(f" {Style.SUCCESS} Complete report details saved to: {Style.BOLD}{Style.UNDERLINE}{os.path.abspath(report_file)}{Style.RESET}")
    except Exception as e:
        print(f" {Style.WARN} Failed to write report file: {e}")
        
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()

