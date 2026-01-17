import streamlit as st
import os
import time
import shutil
import uuid
# 核心：使用 2026 最新版 SDK
from google import genai
from google.genai import types

# ================= 0. 版本元数据 =================
APP_VERSION = "v4.0.4-PRO"
BUILD_DATE = "2026-01-17"

# ================= 1. 初始化页面与安全配置 =================
st.set_page_config(
    page_title=f"凶哥哥的 AI {APP_VERSION}", 
    page_icon="🦁", 
    layout="wide"
)

# 安全读取 Key
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = None

# 初始化 Session State
if "all_sessions" not in st.session_state:
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions = {
        default_id: {
            "title": "新对话", 
            "history": [], # 存储格式：{"role": str, "parts": list}
            "files": [],   # 存储 File 对象引用
            "processed": False 
        }
    }
    st.session_state.current_session_id = default_id

def get_current_session():
    sid = st.session_state.current_session_id
    if sid not in st.session_state.all_sessions:
        sid = list(st.session_state.all_sessions.keys())[0]
        st.session_state.current_session_id = sid
    return st.session_state.all_sessions[sid]

current_session = get_current_session()

# ================= 2. 侧边栏 =================
with st.sidebar:
    st.title("🦁 凶哥哥的 AI")
    st.status(f"v4.0.4 稳定版", state="complete")
    
    with st.expander("⚙️ 模型参数", expanded=True):
        model_list = [
            "gemini-1.5-pro",           # OCR 识图首选
            "gemini-2.5-flash",         # 2026 主力
            "gemini-3-flash-preview",   # 最新极速
        ]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 2.0, 0.5) # 处理文档建议调低
        enable_search = st.toggle("🌍 开启联网搜索", value=True)

    st.divider()
    st.caption("💬 会话管理")
    if st.button("➕ 新建对话", use_container_width=True):
        nid = str(uuid.uuid4()); st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files": [], "processed": False}
        st.session_state.current_session_id = nid; st.rerun()

    for sid in list(st.session_state.all_sessions.keys()):
        sess = st.session_state.all_sessions[sid]
        active = (sid == st.session_state.current_session_id)
        c1, c2 = st.columns([0.8, 0.2])
        with c1:
            if st.button(sess["title"], key=f"s_{sid}", type="primary" if active else "secondary", use_container_width=True):
                st.session_state.current_session_id = sid; st.rerun()
        with c2:
            with st.popover("⋮"):
                new_n = st.text_input("重命名", value=sess["title"], key=f"r_{sid}")
                if new_n != sess["title"]: sess["title"] = new_n; st.rerun()
                if st.button("🗑️", key=f"d_{sid}"):
                    if len(st.session_state.all_sessions) > 1: del st.session_state.all_sessions[sid]; st.rerun()

# ================= 3. 核心功能函数 =================

def get_client():
    if not API_KEY:
        st.error("❌ 未检测到 API KEY")
        return None
    return genai.Client(api_key=API_KEY)

def upload_and_notify(client, files):
    """上传并插入永久通知"""
    temp_dir = "cloud_tmp"
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir)
    
    uploaded_refs = []
    file_names = []
    
    with st.status("🚀 附件解析中...", expanded=True) as status:
        local_paths = []
        for f in files:
            p = os.path.join(temp_dir, f.name); file_names.append(f.name)
            with open(p, "wb") as b: b.write(f.getbuffer())
            local_paths.append(p)
        local_paths.sort()
        
        for path in local_paths:
            try:
                r = client.files.upload(path=path)
                uploaded_refs.append(r)
                st.write(f"✅ 已就绪: {os.path.basename(path)}")
            except Exception as e: st.error(f"出错: {e}")
        
        while True:
            ready = True
            for r in uploaded_refs:
                if client.files.get(name=r.name).state.name == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(1)
        status.update(label="✅ 解析完成", state="complete", expanded=False)
    
    # 插入永久历史提示
    hint_text = f"📎 **系统：已成功挂载 {len(file_names)} 个附件**\n\n" + "\n".join([f"- `{n}`" for n in file_names])
    current_session["history"].append({"role": "system_info", "content": hint_text})
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    return uploaded_refs

# ================= 4. 对话逻辑 =================

client = get_client()
if client:
    # 1. 渲染历史 (支持多模态内容渲染)
    for m in current_session["history"]:
        with st.chat_message("assistant" if m["role"] in ["model", "system_info"] else "user"):
            st.markdown(m["content"])

    # 2. 底部极简上传区与输入框
    chat_prompt = None
    with st.container():
        # 唯一的上传区域：Browse + Drag
        files = st.file_uploader(
            "拖拽图片至此或点击上传 (支持批量)", 
            accept_multiple_files=True, 
            key="main_uploader",
            label_visibility="collapsed" # 隐藏标签，保持极简
        )
        
        # 只要有新文件上传且未处理
        if files and not current_session["files"]:
            if st.button("🚀 确认并开始分析附件", use_container_width=True, type="primary"):
                current_session["files"] = upload_and_notify(client, files)
                current_session["processed"] = False
                st.rerun()

        chat_prompt = st.chat_input("请总结附件内容或针对细节提问...")

    # 3. 对话执行逻辑
    if chat_prompt:
        current_session["history"].append({"role": "user", "content": chat_prompt})
        st.rerun()

    if current_session["history"] and current_session["history"][-1]["role"] == "user":
        with st.chat_message("assistant"):
            box = st.empty(); full = ""
            
            # --- 关键重构：构造多模态 Payload ---
            # 这一轮真正要发给 API 的内容
            current_message_parts = []
            
            # 如果有文件且还没被标记为已处理
            if current_session["files"] and not current_session["processed"]:
                # 注入强力系统指令，强制 AI 关联附件
                current_message_parts.append(types.Part(text="[IMPORTANT SYSTEM INSTRUCTION] User has provided files below. Read them carefully and use them as the primary context for the following question."))
                # 转换所有文件对象为 Part
                for f_ref in current_session["files"]:
                    current_message_parts.append(f_ref) # SDK 会自动识别为 File Part
            
            # 加入用户最新文字提问
            current_message_parts.append(types.Part(text=current_session["history"][-1]["content"]))

            try:
                # --- 历史记录转换器 (核心修复点) ---
                # 将 session_state 里的简易历史转换为 API 需要的复合 Parts 结构
                h_objs = []
                for h in current_session["history"][:-1]:
                    if h["role"] == "system_info":
                        # 系统提示作为 model 的一段确认信息存入，不作为 user 输入
                        h_objs.append(types.Content(role="model", parts=[types.Part(text=h["content"])]))
                    else:
                        h_objs.append(types.Content(
                            role="user" if h["role"] == "user" else "model",
                            parts=[types.Part(text=h["content"])]
                        ))

                tools = [types.Tool(google_search=types.GoogleSearch())] if enable_search else []

                chat_obj = client.chats.create(
                    model=selected_model,
                    history=h_objs,
                    config=types.GenerateContentConfig(temperature=temperature, tools=tools)
                )
                
                # 发送（包含所有附件）
                response = chat_obj.send_message_stream(message=current_message_parts)
                for chunk in response:
                    if chunk.text:
                        full += chunk.text
                        box.markdown(full + "▌")
                
                box.markdown(full)
                
                # 成功后标记
                current_session["processed"] = True 
                current_session["history"].append({"role": "model", "content": full})
                
                # 自动改名
                if len(current_session["history"]) <= 3: # 考虑进了 system_info
                    current_session["title"] = chat_prompt[:10]
                st.rerun()

            except Exception as e:
                st.error(f"对话异常: {e}")
