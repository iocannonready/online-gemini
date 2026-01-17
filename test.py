import streamlit as st
import os
import time
import shutil
import uuid
from google import genai
from google.genai import types

# ================= 0. 元数据 =================
APP_VERSION = "v4.2.5-DIAG"

# ================= 1. 页面配置 =================
st.set_page_config(page_title=f"链路诊断 {APP_VERSION}", layout="wide")

try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = None

# 初始化 Session
if "all_sessions" not in st.session_state:
    st.session_state.all_sessions = {}
if "current_session_id" not in st.session_state or not st.session_state.current_session_id:
    did = str(uuid.uuid4())
    st.session_state.all_sessions[did] = {"title": "诊断会话", "history": [], "files_meta": [], "processed": False}
    st.session_state.current_session_id = did

current_session = st.session_state.all_sessions[st.session_state.current_session_id]

# ================= 2. 侧边栏 =================
with st.sidebar:
    st.title("🦁 链路诊断专家")
    st.info(f"版本: {APP_VERSION}")
    selected_model = st.selectbox("测试模型", ["gemini-2.0-flash", "gemini-1.5-flash"])
    
    if st.button("🔴 彻底重置所有环境"):
        st.session_state.clear()
        st.rerun()

# ================= 3. 核心诊断逻辑 =================

def diagnostic_upload(client, files):
    """全透明上传过程"""
    file_metas = []
    with st.status("🩺 正在追踪文件流向...", expanded=True) as status:
        
        # 🟢 A阶段: Streamlit 接收
        st.write("### [A] Streamlit 接收层")
        for f in files:
            st.write(f"✔️ 浏览器 -> 服务器成功 | 名字: `{f.name}` | 大小: `{f.size/1024:.1f}KB`")

        # 🟢 B阶段: 云端本地存储
        st.write("### [B] 云端磁盘写入层")
        tmp = "diag_tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        for f in files:
            p = os.path.join(tmp, f.name)
            with open(p, "wb") as b: b.write(f.getbuffer())
        st.write(f"✔️ 文件已写入 Streamlit 临时磁盘 `{tmp}/` 目录")

        # 🟢 C阶段: Google 服务器入库
        st.write("### [C] Google File API 握手")
        for f_name in os.listdir(tmp):
            p = os.path.join(tmp, f_name)
            try:
                ext = f_name.lower().split('.')[-1]
                m_type = "application/pdf" if ext == 'pdf' else f"image/{ext.replace('jpg','jpeg')}"
                
                # 执行上传
                r = client.files.upload(path=p, config={"mime_type": m_type})
                
                file_metas.append({"uri": r.uri, "mime_type": r.mime_type, "name": f_name})
                st.write(f"✔️ Google 已收录: `{f_name}`")
                st.write(f"   └ 资源URI: `{r.uri}`")
            except Exception as e:
                st.error(f"❌ Google 拒收文件 `{f_name}`: {e}")

        # 🟢 D阶段: 视觉解析激活
        st.write("### [D] 视觉引擎解析状态 (ACTIVE)")
        for meta in file_metas:
            f_id = meta["uri"].split("/")[-1]
            start = time.time()
            while True:
                f_info = client.files.get(name=f_id)
                if f_info.state.name == "ACTIVE":
                    st.write(f"✔️ 视觉模型解析完成: `{meta['name']}` 状态已变为 ACTIVE")
                    break
                elif f_info.state.name == "FAILED":
                    st.error(f"❌ 视觉模型解析失败: `{meta['name']}`")
                    break
                if time.time() - start > 60:
                    st.warning(f"⏳ `{meta['name']}` 解析超时")
                    break
                time.sleep(2)

        status.update(label="✅ 链路诊断完毕，资源已锁定", state="complete")
    return file_metas

# ================= 4. 主对话区 =================

client = genai.Client(api_key=API_KEY) if API_KEY else None

if client:
    # 渲染历史
    for m in current_session["history"]:
        with st.chat_message("assistant" if m["role"] == "model" else "user"):
            for p in m["parts"]:
                if "text" in p: st.markdown(p["text"])
                if "file_uri" in p: st.code(f"🔗 视觉链接: {p['file_uri']}")

    # 上传与输入
    with st.container():
        if current_session["files_meta"]:
            st.success(f"🧬 AI 当前脑中持有的文件数: {len(current_session['files_meta'])}")
        
        up_fs = st.file_uploader("点击或拖入测试文件 (PDF/图片)", accept_multiple_files=True, key="diag_v5")
        
        if up_fs and not current_session["files_meta"]:
            if st.button("🚀 开始全链路诊断上传"):
                current_session["files_meta"] = diagnostic_upload(client, up_fs)
                st.rerun()

        chat_input = st.chat_input("针对附件提问（例如：总结全文）")

    # 执行对话
    if chat_input:
        user_parts = []
        # 将文件 URI 注入到 payload
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

                # 构建当前消息 Payload
                last_msg = current_session["history"][-1]
                payload = []
                for p in last_msg["parts"]:
                    if "text" in p: payload.append(types.Part(text=p["text"]))
                    elif "file_uri" in p: payload.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))

                # 强力测试指令：让 AI 必须先报数
                test_instruction = """你现在是视觉链路校验员。
                当你收到用户消息时，你的回复必须严格遵循以下格式：
                1. 第一行：'报告！我看到了 X 个 file_uri 对象。' (X是实际数量)
                2. 第二行：列出你看到的 URI 地址。
                3. 第三行：根据这些文件的内容回答用户的问题。"""

                # 创建 Chat 实例
                chat_session = client.chats.create(
                    model=selected_model,
                    history=history_objs,
                    config=types.GenerateContentConfig(
                        system_instruction=test_instruction,
                        temperature=0.0
                    )
                )
                
                # 发送并流式显示
                response = chat_session.send_message_stream(message=payload)
                for chunk in response:
                    if chunk.text:
                        full += chunk.text
                        box.markdown(full + "▌")
                
                box.markdown(full)
                current_session["history"].append({"role": "model", "parts": [{"text": full}]})
                st.rerun()
            except Exception as e:
                st.error(f"❌ 诊断对话层报错: {e}")

else:
    st.warning("👈 请先配置 API Key")
