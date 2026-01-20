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
                    with st.status(f"♻️ 正在自动续期文件: {meta['display_name']}...", expanded=True):
                        st.write("文件已过期，正在从服务器备份重新上传...")
                        r = client.files.upload(file=local_backup, config={"mime_type": meta["mime_type"]})
                        # 更新元数据
                        meta["uri"] = r.uri
                        meta["name"] = r.name
                        # 等待激活
                        while True:
                            if client.files.get(name=r.name).state.name == "ACTIVE": break
                            time.sleep(1)
                        updated = True
                        st.write("✅ 续期成功！")
                except Exception as e:
                    st.error(f"自动续期失败: {e}")
            else:
                st.error(f"❌ 备份文件丢失: {meta['display_name']}")
    
    if updated:
        save_user_data() # 保存新的 URI
    return files_meta

def upload_handler_isolated(client, files):
    u_dir = get_user_dir()
    file_storage_path = os.path.join(u_dir, "files")
    
    new_metas = []
    
    with st.status("☁️ 正在同步并备份文件...", expanded=True) as status:
        for i, f in enumerate(files):
            # 1. 安全重命名
            ext = os.path.splitext(f.name)[1].lower()
            if not ext: ext = ".pdf" if f.type == "application/pdf" else ".jpg"
            # 使用 UUID 确保文件名在文件夹内唯一
            backup_name = f"{uuid.uuid4()}{ext}"
            backup_path = os.path.join(file_storage_path, backup_name)
            
            # 2. 存入用户专属备份文件夹
            with open(backup_path, "wb") as b: b.write(f.getbuffer())
            
            try:
                # 3. 上传 Google
                mime = "application/pdf" if ext == ".pdf" else "image/jpeg"
                if "png" in ext: mime = "image/png"
                
                r = client.files.upload(file=backup_path, config={"mime_type": mime})
                
                new_metas.append({
                    "uri": r.uri, 
                    "mime_type": r.mime_type, 
                    "name": r.name,
                    "display_name": f.name,
                    "backup_name": backup_name # 记录本地备份文件名，用于续期
                })
                st.write(f"✅ 已挂载: {f.name}")
            except Exception as e:
                st.error(f"❌ 上传失败: {f.name} - {e}")
        
        # 4. 轮询
        while True:
            all_ready = True
            for m in new_metas:
                if client.files.get(name=m["name"]).state.name == "PROCESSING":
                    all_ready = False; break
            if all_ready: break
            time.sleep(2)
        status.update(label="✅ 文件处理完成", state="complete", expanded=False)
        
    return new_metas

# ================= 3. 登录页逻辑 =================

if not st.session_state.user_id:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.title("🦁 凶哥哥的 AI")
        st.markdown("---")
        st.info("🔐 请输入访问码 (Access Key) 以进入您的专属空间。")
        
        # 登录表单
        with st.form("login_form"):
            input_code = st.text_input("访问码 / 用户名", placeholder="例如: team_a, user_001")
            submitted = st.form_submit_button("🚀 进入系统", use_container_width=True)
            
            if submitted and input_code.strip():
                st.session_state.user_id = input_code.strip()
                # 加载该用户的数据
                user_data = load_user_data()
                st.session_state.all_sessions = user_data["sessions"]
                st.session_state.current_session_id = user_data["current_id"]
                st.rerun()
    st.stop() # 停止渲染后面的代码，直到登录

# ================= 4. 已登录：侧边栏 =================

current_id = st.session_state.current_session_id
# 容错
if current_id not in st.session_state.all_sessions:
    current_id = list(st.session_state.all_sessions.keys())[0]
    st.session_state.current_session_id = current_id
current_session = st.session_state.all_sessions[current_id]

# 每次页面加载时，检查当前会话的文件是否需要续期
# 为了不影响性能，只在有文件且 session 初始化时检查一次
if "last_check" not in st.session_state:
    client_check = get_client()
    if current_session["files_meta"]:
        smart_file_check(client_check, current_session["files_meta"])
    st.session_state.last_check = True

with st.sidebar:
    st.header(f"👤 用户: {st.session_state.user_id}")
    if st.button("🚪 退出登录"):
        st.session_state.user_id = None
        st.rerun()
        
    st.divider()
    
    # 模型配置
    with st.expander("⚙️ 模型配置", expanded=True):
        model_map = {
            "gemini-2.5-flash-lite": "⚡ 2.5 Lite (10RPM)",
            "gemini-2.5-flash": "🏆 2.5 Flash (推荐)",
            "gemini-3-flash-preview": "🧪 3.0 Flash (预览)"
        }
        selected_key = st.selectbox("模型", list(model_map.keys()), format_func=lambda x: f"{x.replace('gemini-', '')}", index=1)
        temperature = st.slider("创造力", 0.0, 1.0, 0.2)
        enable_search = st.toggle("联网搜索", value=True)

    # 附件管理
    st.subheader("📁 附件管理")
    up_files = st.file_uploader("添加文件", type=['pdf','png','jpg','jpeg'], accept_multiple_files=True, label_visibility="collapsed")
    
    if up_files:
        current_names = [x['display_name'] for x in current_session["files_meta"]]
        new_files = [f for f in up_files if f.name not in current_names]
        if new_files:
            client = get_client()
            new_metas = upload_handler_isolated(client, new_files)
            current_session["files_meta"].extend(new_metas)
            current_session["processed"] = False 
            save_user_data() # 保存
            st.rerun()

    if current_session["files_meta"]:
        with st.container(border=True):
            for f in current_session["files_meta"]: st.caption(f"📎 {f['display_name']}")
            if st.button("🗑️ 清空附件", use_container_width=True):
                current_session["files_meta"] = []; current_session["processed"] = False
                save_user_data(); st.rerun()
    else:
        st.caption("暂无附件")

    st.divider()
    
    # 会话管理
    st.caption("💬 历史会话")
    if st.button("➕ 新建对话", use_container_width=True):
        nid = str(uuid.uuid4())
        st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files_meta": [], "processed": False}
        st.session_state.current_session_id = nid
        save_user_data(); st.rerun()

    session_keys = list(st.session_state.all_sessions.keys())
    for sid in session_keys:
        sess = st.session_state.all_sessions[sid]
        active = (sid == st.session_state.current_session_id)
        c1, c2 = st.columns([0.85, 0.15])
        with c1:
            if st.button(f"{'📂' if active else '⚪'} {sess['title']}", key=f"btn_{sid}", use_container_width=True, type="primary" if active else "secondary"):
                st.session_state.current_session_id = sid; save_user_data(); st.rerun()
        with c2:
            with st.popover("⋮"):
                new_t = st.text_input("重命名", value=sess["title"], key=f"rn_{sid}")
                if new_t != sess["title"]: sess["title"] = new_t; save_user_data(); st.rerun()
                if st.button("🗑️", key=f"del_{sid}"):
                    del st.session_state.all_sessions[sid]; save_user_data(); st.rerun()

# ================= 5. 主聊天界面 =================

client = get_client()

for msg in current_session["history"]:
    with st.chat_message("assistant" if msg["role"] == "model" else "user"):
        for part in msg["parts"]:
            if "text" in part: st.markdown(part["text"])
            if "file_uri" in part: st.caption("📄 [附件已发送]")

prompt = st.chat_input("输入问题...")

if prompt and client:
    # A. 构造 User Content
    user_parts_storage = []
    user_parts_api = []
    
    if current_session["files_meta"] and not current_session["processed"]:
        # 续期检查：发送前再检查一次文件是否有效，防止 404
        current_session["files_meta"] = smart_file_check(client, current_session["files_meta"])
        
        sys_hint = "请基于以下附件内容回答："
        user_parts_storage.append({"text": sys_hint})
        user_parts_api.append(types.Part.from_text(text=sys_hint))
        
        for f in current_session["files_meta"]:
            user_parts_storage.append({"file_uri": f["uri"], "mime_type": f["mime_type"]})
            user_parts_api.append(types.Part.from_uri(file_uri=f["uri"], mime_type=f["mime_type"]))
        
        current_session["processed"] = True

    user_parts_storage.append({"text": prompt})
    user_parts_api.append(types.Part.from_text(text=prompt))
    
    current_session["history"].append({"role": "user", "parts": user_parts_storage})
    save_user_data() # 保存用户输入
    
    # B. 构造 History
    api_history = []
    for h in current_session["history"][:-1]:
        parts_list = []
        for p in h["parts"]:
            if "text" in p:
                parts_list.append(types.Part.from_text(text=p["text"]))
            elif "file_uri" in p:
                parts_list.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))
        api_history.append(types.Content(role=h["role"], parts=parts_list))

    # C. 调用 API
    with st.chat_message("assistant"):
        box = st.empty()
        full_response = ""
        
        try:
            tools_cfg = [types.Tool(google_search=types.GoogleSearch())] if enable_search else None
            
            chat = client.chats.create(
                model=selected_key,
                history=api_history,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    tools=tools_cfg,
                    system_instruction="你是一个全能助手。如果用户提供了文件，请务必基于文件内容回答。"
                )
            )
            
            response_stream = chat.send_message_stream(message=user_parts_api)
            
            for chunk in response_stream:
                if chunk.text:
                    full_response += chunk.text
                    box.markdown(full_response + "▌")
            
            box.markdown(full_response)
            current_session["history"].append({"role": "model", "parts": [{"text": full_response}]})
            
            if len(current_session["history"]) == 2:
                current_session["title"] = prompt[:10]
            
            save_user_data() # 保存 AI 回复
            st.rerun()
            
        except Exception as e:
            err_msg = str(e)
            if "404" in err_msg:
                # 遇到 404 很可能是文件过期了，但 smart_check 没拦住，强制刷新
                st.error("❌ 文件引用失效，正在尝试自动修复，请重试...")
                smart_file_check(client, current_session["files_meta"])
            else:
                st.error(f"出错: {err_msg}")
