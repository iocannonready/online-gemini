import streamlit as st
import os
import time
import shutil
import uuid
import json
from pathlib import Path
# 核心 SDK
from google import genai
from google.genai import types

# ================= 0. 版本与配置 =================
APP_VERSION = "v6.0.0-MULTI-USER"
ROOT_DATA_DIR = "user_data_storage" # 所有用户数据的根目录

st.set_page_config(page_title=f"凶哥哥 AI {APP_VERSION}", page_icon="🦁", layout="wide")

try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ 未配置 Secrets: GOOGLE_API_KEY")
    st.stop()

# ================= 1. 用户身份管理系统 =================

if "user_id" not in st.session_state:
    st.session_state.user_id = None

def get_user_dir():
    """获取当前用户的专属目录"""
    if not st.session_state.user_id: return None
    # 简单的文件系统隔离：user_data_storage/{user_id}/
    user_path = os.path.join(ROOT_DATA_DIR, st.session_state.user_id)
    os.makedirs(user_path, exist_ok=True)
    # 子目录：files
    os.makedirs(os.path.join(user_path, "files"), exist_ok=True)
    return user_path

def load_user_data():
    """读取用户专属的 JSON 数据"""
    u_dir = get_user_dir()
    json_path = os.path.join(u_dir, "history.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except: pass
    
    # 默认初始化
    default_id = str(uuid.uuid4())
    return {
        "sessions": {
            default_id: {"title": "新对话", "history": [], "files_meta": [], "processed": False}
        },
        "current_id": default_id
    }

def save_user_data():
    """保存当前状态到用户的 JSON"""
    if not st.session_state.user_id: return
    u_dir = get_user_dir()
    
    # 构建要保存的数据结构
    data_to_save = {
        "sessions": st.session_state.all_sessions,
        "current_id": st.session_state.current_session_id
    }
    
    with open(os.path.join(u_dir, "history.json"), 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)

# ================= 2. 核心功能函数 =================

def get_client():
    os.environ.pop('HTTP_PROXY', None); os.environ.pop('HTTPS_PROXY', None)
    return genai.Client(api_key=API_KEY)

def smart_file_check(client, files_meta):
    """
    【智能续期逻辑】
    检查文件在 Google 端是否有效，如果过期/丢失，自动从本地备份重传
    """
    updated = False
    u_dir = get_user_dir()
    
    for meta in files_meta:
        need_reupload = False
        try:
            # 检查 Google 端状态
            f_info = client.files.get(name=meta["name"])
            if f_info.state.name == "FAILED":
                need_reupload = True
        except:
            # 报错说明文件在 Google 端已过期或被删
            need_reupload = True
            
        if need_reupload:
            # 尝试从本地备份恢复
            local_backup = os.path.join(u_dir, "files", meta["backup_name"])
            if os.path.exists(local_backup):
                try:
                    wi
