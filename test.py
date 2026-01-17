import streamlit as st
import os
import time
import shutil
import uuid
from google import genai
from google.genai import types

APP_VERSION = "v4.2.4-DIAG"

# ================= 1. 基础配置 =================
st.set_page_config(page_title=f"诊断模式 {APP_VERSION}", layout="wide")

try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = None

# 初始化 Session (强制清理旧的、可能导致报错的数据)
if "all_sessions" not in st.session_state:
    st.session_state.all_sessions = {}
    
if "current_session_id" not in st.session_state or not st.session_state.current_session_id:
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions[default_id] = {"title": "诊断测试", "history": [], "files_meta": [], "processed": False}
    st.session_state.current_session_id = default_id

current_session = st.session_state.all_sessions[st.session_state.current_session_id]

# ================= 2. 侧边栏 =================
with st.sidebar:
    st.title("🦁 链路诊断专家")
    st.warning("当前处于【全链路监控】模式")
    selected_model = st.selectbox("模型", ["gemini-2.0-flash", "gemini-1.5-flash"])
    temperature = st.slider("温度", 0.0, 1.0, 0.0) # 诊断建议设为 0
    if st.button("🔴 彻底清空所有缓存 & 重启"):
        st.session_state.clear()
        st.rerun()

# ================= 3. 核心排查函数 =================

def diagnostic_upload(client, files):
    file_metas = []
    with st.status("🩺 正在进行全链路诊断...", expanded=True) as status:
        
        # 步骤 1: 检查 Streamlit 接收
        st.write("Step 1: 检查 Streamlit 原始接收...")
        for f in files:
            st.write(f"   - 收到文件: `{f.name}` | 大小: `{f.size / 1024:.1f} KB` | 类型: `{f.type}`")

        # 步骤 2: 物理保存
        st.write("Step 2: 写入云端临时磁盘...")
        temp_dir = "diag_tmp"
        shutil.rmtree(temp_dir, ignore_errors=True)
        os.makedirs(temp_dir)
        
        for f in files:
            p = os.path.join(temp_dir, f.name)
            with open(p, "wb") as b: b.write(f.getbuffer())
            
        # 步骤 3: 真正的 Google 上传
        st.write("Step 3: 握手 Google File API...")
        for f_name in os.listdir(temp_dir):
            path = os.path.join(temp_dir, f_name)
            try:
                # 显式识别并打印我们要传给 Google 的 MIME
                ext = f_name.lower().split('.')[-1]
                m_type = "application/pdf" if ext == 'pdf' else f"image/jpeg"
                
                r = client.files.upload(path=path, config={"mime_type": m_type})
                
                # 重要：记录 URI
                file_metas.append({"uri": r.uri, "mime_type": r.mime_type, "name": f_name})
                st.write(f"   - ✅ Google 已入库: `{f_name}`")
                st.write(f"     └─ 内部地址: `{r.uri}`")
            except Exception as e:
                st.error(f"   - ❌ 上传失败: {e}")

        # 步骤 4: 状态轮询
        st.write("Step 4: 等待 Google 后台扫描 (ACTIVE 检查)...")
        for meta in file_metas:
            f_id = meta["uri"].split("/")[-1]
            check_start = time.time()
            while True:
                f_info = client.files.get(name=f_id)
                if f_info.state.name == "ACTIVE":
                    st.write(f"   - 🟢 文件 `{meta['name']}` 激活成功！")
                    break
                elif f_info.state.name == "FAILED":
                    st.error(f"   - 🔴 文件 `{meta['name']}` 被 Google 拒绝解析！")
                    break
                
                if time.time() - check_start > 60: # 1分钟限制
                    st.warning(f"   - ⏳ 文件 `{meta['name']}` 扫描超时")
                    break
                time.sleep(2)

        status.update(label="✅ 诊断环节结束，请开始提问", state="complete")
    return file_metas

# ================= 4. 主界面逻辑 =================

client = genai.Client(api_key=API_KEY) if API_KEY else None

if client:
    # 渲染历史
    for m in current_session["history"]:
        with st.chat_message("assistant" if m["role"] == "model" else "user"):
            for p in m["parts"]:
                if "text" in p: st.markdown(p["text"])
                if "file_uri" in p: st.code(f"🔗 已挂载文件: {p['file_uri']}")

    # 输入与上传
    with st.container():
        # 显示当前会话持有的文件引用
        if current_session["files_meta"]:
            st.info(f"🧬 当前会话活跃文件数: {len(current_session['files_meta'])}")
        
        up_fs = st.file_uploader("诊断上传", accept_multiple_files=True, key="diag_up")
        
        if up_fs and not current_session["files_meta"]:
            if st.button("🚀 执行全链路诊断上传"):
                current_session["files_meta"] = diagnostic_upload(client, up_fs)
                current_session["processed"] = False
                st.rerun()

        chat_input = st.chat_input("输入问题...")

    if chat_input:
        # 构造 Payload
        user_parts = []
        # 如果是新文件，强制注入。注意：我们不再把文件放第一句话，我们每一句都带上文件试试
        if current_session["files_meta"]:
            for f in current_session["files_meta"]:
                user_parts.append({"file_uri": f["uri"], "mime_type": f["mime_type"]})
        
        user_parts.append({"text": chat_input})
        current_session["history"].append({"role": "user", "parts": user_parts})
        st.rerun()

    if current_session["history"] and current_session["history"][-1]["role"] == "user":
        with st.chat_message("assistant"):
            box = st.empty(); full = ""
            try:
                # 转换历史
                history_objs = []
                for h in current_session["history"][:-1]:
                    p_objs = []
                    for p in h["parts"]:
                        if "text" in p: p_objs.append(types.Part(text=p["text"]))
                        elif "file_uri" in p: p_objs.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))
                    history_objs.append(types.Content(role=h["role"], parts=p_objs))

                # 最后一条
                last_msg = current_session["history"][-1]
                payload = []
                for p in last_msg["parts"]:
                    if "text" in p: payload.append(types.Part(text=p["text"]))
                    elif "file_uri" in p: payload.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))

                st.write("🔍 **DEBUG: 正在向服务器发送的 Payload 数量:**", len(payload))
                
                chat_session = client.chats.create(
                    model=selected_model,
                    history=history_objs,
                    config=types.Generate
