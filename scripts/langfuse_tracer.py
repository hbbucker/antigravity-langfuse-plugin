#!/usr/bin/env python3
"""
Langfuse Tracer for Antigravity CLI (agy)
Captures execution transcripts, generations, reasoning (thinking), tokens, tool calls,
and links each turn, child subagents, and skills hierarchically within a unified conversation Session.
"""
import sys
import os
import json
import re
import glob
import hashlib
from datetime import datetime
import urllib.request
import urllib.error

def normalize_path_separators(path_str: str) -> str:
    """Normaliza separadores Windows para formato POSIX para regex e caminhos uniformes."""
    if not path_str or not isinstance(path_str, str):
        return ""
    return str(path_str).replace("\\", "/")

def resolve_langfuse_config(workspace_paths=None) -> dict:
    """
    Resolve as configurações do Langfuse respeitando a hierarquia de precedência:
    1. Variáveis de ambiente (LANGFUSE_HOST / LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)
    2. Arquivo de workspace (.langfuse.env ou .env)
    3. Arquivo global do usuário (~/.gemini/antigravity-cli/langfuse.json)
    4. Fallback padrão local (Docker localhost:3000)
    """
    host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL")
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")

    # 2. Workspace config
    if workspace_paths and not (host and public_key and secret_key):
        for ws in workspace_paths:
            if not ws:
                continue
            for fname in (".langfuse.env", ".env"):
                env_file = os.path.join(ws, fname)
                if os.path.exists(env_file):
                    try:
                        with open(env_file, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith("#") and "=" in line:
                                    k, v = line.split("=", 1)
                                    k, v = k.strip(), v.strip().strip('"').strip("'")
                                    if k in ("LANGFUSE_HOST", "LANGFUSE_BASE_URL") and not host:
                                        host = v
                                    elif k == "LANGFUSE_PUBLIC_KEY" and not public_key:
                                        public_key = v
                                    elif k == "LANGFUSE_SECRET_KEY" and not secret_key:
                                        secret_key = v
                    except Exception:
                        pass

    # 3. Global user config
    user_config_path = os.path.expanduser("~/.gemini/antigravity-cli/langfuse.json")
    if os.path.exists(user_config_path) and not (host and public_key and secret_key):
        try:
            with open(user_config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if not host:
                    host = cfg.get("host") or cfg.get("baseUrl")
                if not public_key:
                    public_key = cfg.get("publicKey")
                if not secret_key:
                    secret_key = cfg.get("secretKey")
        except Exception:
            pass

    # 4. Fallback padrão local Docker
    if not host:
        host = "http://localhost:3000"
    if not public_key:
        public_key = "pk-lf-antigravity-cli-public"
    if not secret_key:
        secret_key = "sk-lf-antigravity-cli-secret"

    if host.endswith("/"):
        host = host[:-1]

    return {
        "host": host,
        "public_key": public_key,
        "secret_key": secret_key
    }

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-lf-antigravity-cli-public")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "sk-lf-antigravity-cli-secret")

STATE_FILE = os.path.expanduser("~/.gemini/antigravity-cli/cache/langfuse_state.json")
BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity-cli/brain")

def is_langfuse_healthy(host: str = None) -> bool:
    target_host = host or LANGFUSE_HOST
    try:
        url = f"{target_host}/api/public/health"
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "antigravity-langfuse-tracer")
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            return resp.status == 200
    except Exception:
        # Se for cloud.langfuse.com ou https remoto, não aborta preventivamente
        if target_host and ("cloud.langfuse.com" in target_host or target_host.startswith("https://")):
            return True
        return False

def get_trace_id(seed: str) -> str:
    cleaned = seed.replace("-", "").lower()
    if len(cleaned) == 32 and all(c in "0123456789abcdef" for c in cleaned):
        return cleaned
    return hashlib.md5(seed.encode("utf-8")).hexdigest()

def normalize_model_name(raw_name: str, fallback_parent: str = "gemini-3.8-flash") -> str:
    """Normaliza o nome do modelo para corresponder à tabela de preços do Langfuse."""
    if not raw_name or raw_name in ("auto", "inherit"):
        return fallback_parent
    
    cleaned = str(raw_name).replace('"', '').strip().lower()
    cleaned = re.sub(r"\s*\([^)]*\)", "", cleaned).strip()
    cleaned = cleaned.replace(" ", "-")
    
    if "flash-lite" in cleaned or "flash_lite" in cleaned:
        return "gemini-2.5-flash"
    if "3.8-flash" in cleaned or "3-flash" in cleaned or cleaned == "flash":
        return "gemini-3.8-flash"
    if "2.5-pro" in cleaned or "2-pro" in cleaned or cleaned == "pro":
        return "gemini-2.5-pro"
    if "2.5-flash" in cleaned:
        return "gemini-2.5-flash"
    if "2.0-flash" in cleaned:
        return "gemini-2.0-flash"
    if "4-argon" in cleaned or "argon" in cleaned:
        return "gemini-4-argon"
    return cleaned

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state: dict):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass

def get_installed_skills_map(workspace_paths=None) -> dict:
    """Descobre todas as skills instaladas no sistema e no workspace."""
    search_dirs = [
        os.path.expanduser("~/.gemini/antigravity-cli/skills"),
        os.path.expanduser("~/.gemini/antigravity-cli/builtin/skills"),
    ]
    for p in glob.glob(os.path.expanduser("~/.gemini/config/plugins/*/skills")):
        search_dirs.append(p)
    
    if workspace_paths:
        for ws in workspace_paths:
            search_dirs.append(os.path.join(ws, ".agents", "skills"))
            search_dirs.append(os.path.join(ws, ".gemini", "skills"))
            search_dirs.append(os.path.join(ws, "skills"))

    skills = {}
    for sdir in search_dirs:
        if not os.path.isdir(sdir):
            continue
        try:
            for item in os.listdir(sdir):
                item_path = os.path.join(sdir, item)
                skill_md = os.path.join(item_path, "SKILL.md")
                if os.path.isdir(item_path) and os.path.exists(skill_md):
                    skills[item] = skill_md
        except Exception:
            continue
    return skills

def format_skills_available(skills_map: dict, priority_skills=None) -> list:
    """Monta a lista de skills_available para o Langfuse, respeitando o limite rígido de 100."""
    available = []
    seen = set()
    
    if priority_skills:
        for p in priority_skills:
            if p in skills_map and p not in seen:
                available.append({"name": p, "version": 1})
                seen.add(p)
                
    for name in sorted(skills_map.keys()):
        if name not in seen:
            available.append({"name": name, "version": 1})
            seen.add(name)
        if len(available) >= 95:
            break
            
    return available

def detect_skill_load(tool_name: str, tool_args: dict, skills_map: dict) -> dict:
    """Detecta se uma chamada de ferramenta representa o carregamento/leitura de uma skill."""
    if not isinstance(tool_args, dict):
        return None
    
    raw_path = tool_args.get("Path") or tool_args.get("path") or tool_args.get("file_path") or ""
    path = normalize_path_separators(raw_path)
    if not path and tool_name == "run_command":
        cmd = tool_args.get("CommandLine") or tool_args.get("command") or ""
        cmd_norm = normalize_path_separators(cmd)
        m = re.search(r'(?:^|[\s"\'])(/[^\s"\']+/skills/([a-zA-Z0-9_\-]+)/[^\s"\']+)', cmd_norm)
        if m:
            path = m.group(1)
            
    if not path or not isinstance(path, str):
        return None
        
    m = re.search(r'/skills/([a-zA-Z0-9_\-]+)/', path)
    if m:
        skill_name = m.group(1)
        # Caminho canônico para SKILL.md se existir
        skill_path = skills_map.get(skill_name, path)
        return {
            "skillName": skill_name,
            "filePath": skill_path
        }
        
    return None

def detect_startupos_context(text: str = "", steps: list = None, workspace_paths: list = None) -> dict:
    """
    Detecta automaticamente o contexto de Feature e Stage do framework StartupOS / TLC v4:
    1. Acessos a arquivos (.specs/features/<slug>/...) e ferramentas
    2. Comandos ou texto do prompt (/specify <slug>, Feature Slug: <slug>, etc.)
    3. Worktrees do Orca ou branches Git do workspace
    """
    feature = None
    stage = None

    # 1. Inspeção de chamadas de ferramentas e arquivos acessados
    if steps:
        for s in steps:
            for t in s.get("tool_calls", []) or []:
                args = t.get("args", {})
                if not isinstance(args, dict):
                    continue
                raw_path = (
                    args.get("Path") or args.get("path") or 
                    args.get("file_path") or args.get("CommandLine") or 
                    args.get("command") or ""
                )
                path_val = normalize_path_separators(raw_path)
                if isinstance(path_val, str) and path_val:
                    m_feat = re.search(r'\.specs/features/([a-zA-Z0-9_\-]+)', path_val)
                    if m_feat:
                        feature = m_feat.group(1)
                    if "/spec.md" in path_val:
                        stage = stage or "specify"
                    elif "/design.md" in path_val or "/plan.md" in path_val:
                        stage = stage or "design"
                    elif "/tasks.md" in path_val or "/tasks/" in path_val:
                        stage = stage or "tasks"
                    elif "/proofs.md" in path_val or "/verification.md" in path_val or "/qa/" in path_val:
                        stage = stage or "validate"
                    elif "/pr.md" in path_val:
                        stage = stage or "pr"

    # 2. Inspeção de texto do prompt / comandos do StartupOS
    if text:
        text_norm = normalize_path_separators(text)
        if not feature:
            m_slug = re.search(r'Feature\s+Slug:\s*[`\'"]?([a-zA-Z0-9_\-]+)[`\'"]?', text_norm, re.IGNORECASE)
            if m_slug:
                feature = m_slug.group(1)
        if not feature:
            m_path = re.search(r'\.specs/features/([a-zA-Z0-9_\-]+)', text_norm)
            if m_path:
                feature = m_path.group(1)
        if not feature:
            m_cmd = re.search(r'/(?:specify|spec|design|plan|tasks|task|execute|implement|validate|verify|qa|review)\s+([a-zA-Z0-9_\-]+)', text_norm, re.IGNORECASE)
            if m_cmd:
                feature = m_cmd.group(1)
        if not feature:
            m_feat = re.search(r'(?:feature|feat)[:\s=]+[`\'"]?([a-zA-Z0-9_\-]+)[`\'"]?', text_norm, re.IGNORECASE)
            if m_feat:
                cand = m_feat.group(1).lower()
                if cand not in ("slug", "true", "false", "none", "null", "the", "a", "nova"):
                    feature = m_feat.group(1)

        lower_text = text_norm.lower()
        if not stage:
            if re.search(r'/(?:specify|spec)\b', lower_text) or "etapa specify" in lower_text or "fase 1" in lower_text:
                stage = "specify"
            elif re.search(r'/(?:design|plan)\b', lower_text) or "etapa design" in lower_text or "etapa plan" in lower_text:
                stage = "design"
            elif re.search(r'/(?:tasks|task)\b', lower_text) or "etapa tasks" in lower_text or "fase 3" in lower_text:
                stage = "tasks"
            elif re.search(r'/(?:execute|implement)\b', lower_text) or "etapa implement" in lower_text or "como maker" in lower_text:
                stage = "execute"
            elif re.search(r'/(?:validate|verify)\b', lower_text) or "etapa validate" in lower_text or "qa lead" in lower_text:
                stage = "validate"
            elif "/qa" in lower_text or "auditoria de qa" in lower_text:
                stage = "qa"
            elif "/pr" in lower_text or "pronta para pr" in lower_text:
                stage = "pr"

    # 3. Inspeção de workspace paths e branches Git
    if not feature and workspace_paths:
        for wp in workspace_paths:
            wp_norm = normalize_path_separators(wp)
            m_ws = re.search(r'/workspaces/startupos/([a-zA-Z0-9_\-]+)', wp_norm)
            if m_ws:
                feature = m_ws.group(1)
                break
            if os.path.exists(os.path.join(wp, ".git")):
                try:
                    import subprocess
                    branch = subprocess.check_output(
                        ["git", "-C", wp, "rev-parse", "--abbrev-ref", "HEAD"],
                        stderr=subprocess.DEVNULL, text=True, timeout=1
                    ).strip()
                    m_br = re.search(r'^(?:feat(?:ure)?/)?([a-zA-Z0-9_\-]+)$', branch)
                    if m_br and branch not in ("main", "master", "develop"):
                        feature = m_br.group(1)
                        break
                except Exception:
                    pass

    return {
        "feature": feature,
        "stage": stage
    }

def find_parent_info_for_subagent(sub_id: str, parent_conv_id: str) -> dict:
    """Procura no transcript do pai o comando invoke_subagent que criou o subagente."""
    parent_path = os.path.join(BRAIN_DIR, parent_conv_id, ".system_generated", "logs", "transcript.jsonl")
    info = {"role": "subagent", "prompt": "", "model": "inherit", "turn_step": 0}
    if not os.path.exists(parent_path):
        return info
    
    try:
        with open(parent_path, "r", encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        
        current_turn_step = 0
        for idx, d in enumerate(lines):
            if d.get("source") == "USER_EXPLICIT" and d.get("type") == "USER_INPUT":
                current_turn_step = d.get("step_index", 0)
            
            if sub_id in str(d.get("content", "")):
                info["turn_step"] = current_turn_step
                if idx > 0:
                    prev = lines[idx - 1]
                    for t in prev.get("tool_calls", []):
                        if t.get("name") == "invoke_subagent":
                            args = t.get("args", {})
                            info["role"] = str(args.get("Role", "subagent")).strip('"')
                            info["prompt"] = str(args.get("Prompt", "")).strip('"')
                            info["model"] = str(args.get("Model", "inherit")).strip('"')
                break
    except Exception:
        pass
    return info

def sync_subagent(client, sub_id: str, sub_info: dict, state: dict, user_id: str, parent_model: str = "gemini-3.8-flash", skills_map: dict = None):
    """Sincroniza os passos e gerações de um subagente aninhando-os sob um span tipo AGENT."""
    sub_transcript = os.path.join(BRAIN_DIR, sub_id, ".system_generated", "logs", "transcript.jsonl")
    if not os.path.exists(sub_transcript):
        return

    last_synced_step = state.get(sub_id, -1)
    sub_steps_to_sync = []
    
    try:
        with open(sub_transcript, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                idx = d.get("step_index", -1)
                if idx > last_synced_step:
                    sub_steps_to_sync.append(d)
    except Exception:
        return

    if not sub_steps_to_sync:
        return

    if skills_map is None:
        skills_map = get_installed_skills_map()

    # Identifica skills prioritárias usadas pelo subagente
    priority_skills = []
    for step in sub_steps_to_sync:
        for tool in step.get("tool_calls", []) or []:
            s_info = detect_skill_load(tool.get("name", ""), tool.get("args", {}), skills_map)
            if s_info and s_info["skillName"] not in priority_skills:
                priority_skills.append(s_info["skillName"])

    available_skills = format_skills_available(skills_map, priority_skills=priority_skills)

    role = sub_info.get("role", "subagent")
    prompt = sub_info.get("prompt", "")
    sub_model_raw = sub_info.get("model", "inherit")
    normalized_sub_model = normalize_model_name(sub_model_raw, fallback_parent=parent_model)
    turn_trace_id = sub_info.get("turn_trace_id")
    session_id = sub_info.get("session_id")
    parent_conv_id = sub_info.get("parent_conv_id", "")

    feature = sub_info.get("feature")
    stage = sub_info.get("stage")

    if not feature or not stage:
        sub_ctx = detect_startupos_context(text=prompt, steps=sub_steps_to_sync)
        if not feature:
            feature = sub_ctx.get("feature")
        if not stage:
            stage = sub_ctx.get("stage")

    sub_tags = ["antigravity-cli", "subagent", normalized_sub_model]
    if feature:
        sub_tags.append("framework:startupos")
        sub_tags.append(f"feature:{feature}")
    if stage:
        sub_tags.append(f"stage:{stage}")
    for ps in priority_skills:
        sub_tags.append(f"skill:{ps}")

    from langfuse import propagate_attributes

    prop_kwargs = {
        "session_id": session_id,
        "user_id": user_id,
        "tags": sub_tags,
        "skills_available": available_skills
    }
    if feature:
        prop_kwargs["version"] = f"feature/{feature}"
        prop_kwargs["metadata"] = {"feature": feature, "framework": "startupos"}
        if stage:
            prop_kwargs["metadata"]["stage"] = stage

    with propagate_attributes(**prop_kwargs):
        # Abre observação do subagente com tipo 'agent'
        subagent_metadata = {
            "subagent_id": sub_id,
            "parent_conversation_id": parent_conv_id,
            "session_id": session_id,
            "model": sub_model_raw,
            "role": role
        }
        if feature:
            subagent_metadata["feature"] = feature
            subagent_metadata["framework"] = "startupos"
        if stage:
            subagent_metadata["stage"] = stage

        try:
            subagent_obs = client.start_observation(
                trace_context={"trace_id": turn_trace_id},
                name=f"subagent:{role}",
                as_type="agent",
                input={"role": role, "prompt": prompt[:2000] if prompt else ""},
                metadata=subagent_metadata
            )
        except Exception:
            return

        max_step = last_synced_step
        final_response = ""

        pending_child_role = ""
        pending_child_prompt = ""
        pending_child_model = ""

        for step in sub_steps_to_sync:
            idx = step.get("step_index", 0)
            source = step.get("source", "")
            step_type = step.get("type", "")

            if source == "MODEL" and step_type == "PLANNER_RESPONSE":
                content = step.get("content", "")
                thinking = step.get("thinking", "")
                in_tokens = step.get("input_tokens", 0) or 0
                out_tokens = step.get("output_tokens", 0) or 0
                cache_tokens = step.get("cache_read_tokens", 0) or 0
                tool_calls = step.get("tool_calls", [])

                if content:
                    final_response = content

                output_payload = {}
                if content:
                    output_payload["response"] = content
                if thinking:
                    output_payload["thinking"] = thinking

                usage_dict = {
                    "input": in_tokens,
                    "output": out_tokens,
                    "total": in_tokens + out_tokens
                }
                if cache_tokens:
                    usage_dict["cache_read"] = cache_tokens

                # Geração filha aninhada diretamente em subagent_obs
                try:
                    sub_gen_meta = {
                        "step_index": idx,
                        "subagent_id": sub_id,
                        "parent_conversation_id": parent_conv_id,
                        "session_id": session_id,
                        "role": role
                    }
                    if feature:
                        sub_gen_meta["feature"] = feature
                        sub_gen_meta["framework"] = "startupos"
                    if stage:
                        sub_gen_meta["stage"] = stage

                    gen_obs = subagent_obs.start_observation(
                        name=f"{role}:generation",
                        as_type="generation",
                        model=normalized_sub_model,
                        input=prompt[:500] if idx <= 2 else f"subagent-step-{idx}",
                        output=output_payload,
                        usage_details=usage_dict,
                        metadata=sub_gen_meta
                    )
                    gen_obs.end()
                except Exception:
                    pass

                # Ferramentas chamadas pelo subagente aninhadas sob subagent_obs
                for t_idx, tool in enumerate(tool_calls):
                    t_name = tool.get("name", "tool")
                    t_args = tool.get("args", {})

                    if t_name == "invoke_subagent":
                        pending_child_role = str(t_args.get("Role", "subagent")).strip('"')
                        pending_child_prompt = str(t_args.get("Prompt", "")).strip('"')
                        pending_child_model = str(t_args.get("Model", "inherit")).strip('"')

                    # Rastreamento nativo de Skills no Langfuse
                    skill_load = detect_skill_load(t_name, t_args, skills_map)
                    if skill_load:
                        try:
                            skill_obs = subagent_obs.start_observation(
                                name="readFile",
                                as_type="tool",
                                input={"path": skill_load["filePath"], "file_path": skill_load["filePath"], "skill": skill_load["skillName"]},
                                output="Loaded skill resource successfully",
                                metadata={
                                    "step_index": idx,
                                    "tool_index": t_idx,
                                    "skill_name": skill_load["skillName"],
                                    "original_tool": t_name
                                }
                            )
                            skill_obs.end()
                        except Exception:
                            pass

                    try:
                        tool_obs = subagent_obs.start_observation(
                            name=f"tool:{t_name}",
                            as_type="tool",
                            input=t_args,
                            metadata={
                                "step_index": idx,
                                "tool_index": t_idx,
                                "subagent_id": sub_id,
                                "session_id": session_id
                            }
                        )
                        tool_obs.end()
                    except Exception:
                        pass

            elif source == "MODEL" and step_type == "GENERIC":
                tool_result = step.get("content", "")
                status = step.get("status", "DONE")

                # Detecta subagente recursivo se houver
                if isinstance(tool_result, str) and "Created the following subagent:" in tool_result:
                    m = re.search(r'"conversationId":\s*"([a-f0-9\-]+)"', tool_result)
                    if m:
                        child_sub_id = m.group(1)
                        child_ctx = detect_startupos_context(text=pending_child_prompt)
                        child_feat = child_ctx.get("feature") or feature
                        child_stg = child_ctx.get("stage") or stage

                        state.setdefault("subagents", {})[child_sub_id] = {
                            "parent_conv_id": sub_id,
                            "session_id": session_id,
                            "turn_trace_id": turn_trace_id,
                            "role": pending_child_role or "subagent",
                            "prompt": pending_child_prompt,
                            "model": pending_child_model or sub_model_raw,
                            "feature": child_feat,
                            "stage": child_stg
                        }

                try:
                    span_obs = subagent_obs.start_observation(
                        name="tool-result",
                        as_type="span",
                        output=tool_result[:5000] if isinstance(tool_result, str) else tool_result,
                        status_message=status if status != "DONE" else None,
                        level="ERROR" if status == "ERROR" else "DEFAULT",
                        metadata={
                            "step_index": idx,
                            "subagent_id": sub_id,
                            "session_id": session_id
                        }
                    )
                    span_obs.end()
                except Exception:
                    pass

            if idx > max_step:
                max_step = idx

        if final_response:
            try:
                subagent_obs.update(output={"response": final_response[:4000]})
            except Exception:
                pass
        
        try:
            subagent_obs.end()
        except Exception:
            pass

        state[sub_id] = max_step

def main():
    output = {}

    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            print(json.dumps(output))
            return

        payload = json.loads(raw_input)
    except Exception:
        print(json.dumps(output))
        return

    conv_id = payload.get("conversationId", "")
    transcript_path = payload.get("transcriptPath", "")
    workspace_paths = payload.get("workspacePaths", [])
    model_name = payload.get("modelName", "auto")

    if not conv_id or not transcript_path or not os.path.isfile(transcript_path):
        print(json.dumps(output))
        return

    lf_config = resolve_langfuse_config(workspace_paths)
    target_host = lf_config.get("host") or LANGFUSE_HOST
    target_pub_key = lf_config.get("public_key") or LANGFUSE_PUBLIC_KEY
    target_sec_key = lf_config.get("secret_key") or LANGFUSE_SECRET_KEY

    # Fail-safe: if local/remote Langfuse is offline or unreachable, exit silently without blocking CLI
    if not is_langfuse_healthy(target_host):
        print(json.dumps(output))
        return

    try:
        from langfuse import Langfuse, propagate_attributes
        client = Langfuse(
            public_key=target_pub_key,
            secret_key=target_sec_key,
            host=target_host
        )
    except Exception:
        print(json.dumps(output))
        return

    user_id = os.environ.get("USER", "bucker")
    state = load_state()
    skills_map = get_installed_skills_map(workspace_paths)

    # 1. Verifica se a conversa atual é um subagente
    is_subagent = False
    parent_sender = None
    subagent_prompt = ""

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            if first_line:
                first_step = json.loads(first_line)
                if first_step.get("source") == "SYSTEM":
                    c = first_step.get("content", "")
                    m = re.search(r"sender=([a-f0-9\-]+)", c)
                    if m:
                        is_subagent = True
                        parent_sender = m.group(1)
                        pm = re.search(r"content=(.*)", c, re.DOTALL)
                        if pm:
                            subagent_prompt = pm.group(1).strip()
    except Exception:
        pass

    if is_subagent and parent_sender:
        sub_info = state.get("subagents", {}).get(conv_id)
        if not sub_info:
            discovered = find_parent_info_for_subagent(conv_id, parent_sender)
            turn_step = discovered.get("turn_step", 0)
            sub_info = {
                "parent_conv_id": parent_sender,
                "session_id": parent_sender,
                "turn_trace_id": get_trace_id(f"{parent_sender}_turn_{turn_step}"),
                "role": discovered.get("role", "subagent"),
                "prompt": discovered.get("prompt") or subagent_prompt,
                "model": discovered.get("model", model_name)
            }
            state.setdefault("subagents", {})[conv_id] = sub_info

        # Enriquecer com feature/stage se ainda não presentes
        if not sub_info.get("feature"):
            feat_ctx = detect_startupos_context(text=sub_info.get("prompt") or subagent_prompt, workspace_paths=workspace_paths)
            if feat_ctx.get("feature"):
                sub_info["feature"] = feat_ctx["feature"]
            if feat_ctx.get("stage"):
                sub_info["stage"] = feat_ctx["stage"]

        sync_subagent(client, conv_id, sub_info, state, user_id, parent_model=normalize_model_name(model_name), skills_map=skills_map)
        try:
            client.flush()
        except Exception:
            pass
        save_state(state)
        print(json.dumps(output))
        return

    # 2. Conversa Principal (Supervisor)
    session_id = conv_id
    normalized_model = normalize_model_name(model_name)
    last_synced_step = state.get(conv_id, -1)

    steps_to_sync = []
    current_user_prompt = payload.get("lastUserInput", "")
    current_turn_step = 0

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    step = json.loads(line)
                    idx = step.get("step_index", -1)

                    if step.get("source") == "USER_EXPLICIT" and step.get("type") == "USER_INPUT":
                        content = step.get("content", "")
                        if content:
                            current_user_prompt = content
                        current_turn_step = idx

                    if idx > last_synced_step:
                        step["_turn_prompt"] = current_user_prompt
                        step["_turn_step"] = current_turn_step
                        steps_to_sync.append(step)
                except Exception:
                    continue
    except Exception:
        print(json.dumps(output))
        return

    max_step_synced = last_synced_step
    pending_sub_role = ""
    pending_sub_prompt = ""
    pending_sub_model = ""

    # Identifica contexto StartupOS (feature e stage)
    active_feature = state.get(f"{conv_id}_feature")
    active_stage = state.get(f"{conv_id}_stage")

    detected_ctx = detect_startupos_context(
        text=current_user_prompt,
        steps=steps_to_sync,
        workspace_paths=workspace_paths
    )

    if detected_ctx.get("feature"):
        active_feature = detected_ctx["feature"]
        state[f"{conv_id}_feature"] = active_feature

    if detected_ctx.get("stage"):
        active_stage = detected_ctx["stage"]
        state[f"{conv_id}_stage"] = active_stage

    # Identifica skills prioritárias usadas no turno
    priority_skills = []
    for step in steps_to_sync:
        for tool in step.get("tool_calls", []) or []:
            s_info = detect_skill_load(tool.get("name", ""), tool.get("args", {}), skills_map)
            if s_info and s_info["skillName"] not in priority_skills:
                priority_skills.append(s_info["skillName"])

    available_skills = format_skills_available(skills_map, priority_skills=priority_skills)

    trace_tags = ["antigravity-cli", "parent:supervisor", normalized_model]
    if active_feature:
        trace_tags.append("framework:startupos")
        trace_tags.append(f"feature:{active_feature}")
    if active_stage:
        trace_tags.append(f"stage:{active_stage}")
    for ps in priority_skills:
        trace_tags.append(f"skill:{ps}")

    for step in steps_to_sync:
        idx = step.get("step_index", 0)
        source = step.get("source", "")
        step_type = step.get("type", "")
        turn_step = step.get("_turn_step", 0)
        turn_prompt = step.get("_turn_prompt", current_user_prompt)

        turn_trace_id = get_trace_id(f"{conv_id}_turn_{turn_step}")
        prompt_snippet = turn_prompt.strip().replace("\n", " ")[:60]
        if active_feature:
            trace_name = f"Feature: {active_feature}"
        else:
            trace_name = f"Turn {turn_step}: {prompt_snippet}" if prompt_snippet else f"Turn {turn_step}"

        trace_metadata = {
            "role": "supervisor",
            "workspace": workspace_paths,
            "turn_step": turn_step,
            "prompt_snippet": prompt_snippet
        }
        if active_feature:
            trace_metadata["feature"] = active_feature
            trace_metadata["framework"] = "startupos"
        if active_stage:
            trace_metadata["stage"] = active_stage

        prop_kwargs = {
            "session_id": session_id,
            "user_id": user_id,
            "trace_name": trace_name,
            "tags": trace_tags,
            "metadata": trace_metadata,
            "skills_available": available_skills
        }
        if active_feature:
            prop_kwargs["version"] = f"feature/{active_feature}"

        with propagate_attributes(**prop_kwargs):
            if source == "MODEL" and step_type == "PLANNER_RESPONSE":
                content = step.get("content", "")
                thinking = step.get("thinking", "")
                in_tokens = step.get("input_tokens", 0) or 0
                out_tokens = step.get("output_tokens", 0) or 0
                cache_tokens = step.get("cache_read_tokens", 0) or 0
                tool_calls = step.get("tool_calls", [])

                output_payload = {}
                if content:
                    output_payload["response"] = content
                if thinking:
                    output_payload["thinking"] = thinking

                usage_dict = {
                    "input": in_tokens,
                    "output": out_tokens,
                    "total": in_tokens + out_tokens
                }
                if cache_tokens:
                    usage_dict["cache_read"] = cache_tokens

                gen_metadata = {
                    "step_index": idx,
                    "turn_step": turn_step,
                    "conversation_id": conv_id,
                    "session_id": session_id,
                    "raw_model": model_name,
                    "workspace": workspace_paths,
                    "role": "supervisor"
                }
                if active_feature:
                    gen_metadata["feature"] = active_feature
                    gen_metadata["framework"] = "startupos"
                if active_stage:
                    gen_metadata["stage"] = active_stage

                try:
                    obs = client.start_observation(
                        trace_context={"trace_id": turn_trace_id},
                        name=f"Turn {turn_step}: Generation" if active_feature else "model-generation",
                        as_type="generation",
                        model=normalized_model,
                        input=turn_prompt,
                        output=output_payload,
                        usage_details=usage_dict,
                        metadata=gen_metadata
                    )
                    obs.end()
                except Exception:
                    pass

                for t_idx, tool in enumerate(tool_calls):
                    t_name = tool.get("name", "tool")
                    t_args = tool.get("args", {})

                    if t_name == "invoke_subagent":
                        pending_sub_role = str(t_args.get("Role", "subagent")).strip('"')
                        pending_sub_prompt = str(t_args.get("Prompt", "")).strip('"')
                        pending_sub_model = str(t_args.get("Model", "inherit")).strip('"')

                    # Rastreamento nativo de Skills no Langfuse
                    skill_load = detect_skill_load(t_name, t_args, skills_map)
                    if skill_load:
                        try:
                            skill_obs = client.start_observation(
                                trace_context={"trace_id": turn_trace_id},
                                name="readFile",
                                as_type="tool",
                                input={"path": skill_load["filePath"], "file_path": skill_load["filePath"], "skill": skill_load["skillName"]},
                                output="Loaded skill resource successfully",
                                metadata={
                                    "step_index": idx,
                                    "tool_index": t_idx,
                                    "skill_name": skill_load["skillName"],
                                    "original_tool": t_name
                                }
                            )
                            skill_obs.end()
                        except Exception:
                            pass

                    try:
                        tool_obs = client.start_observation(
                            trace_context={"trace_id": turn_trace_id},
                            name=f"tool:{t_name}",
                            as_type="tool",
                            input=t_args,
                            metadata={
                                "step_index": idx,
                                "tool_index": t_idx,
                                "conversation_id": conv_id,
                                "session_id": session_id
                            }
                        )
                        tool_obs.end()
                    except Exception:
                        pass

            elif source == "MODEL" and step_type == "GENERIC":
                tool_result = step.get("content", "")
                status = step.get("status", "DONE")

                if isinstance(tool_result, str) and "Created the following subagent:" in tool_result:
                    m = re.search(r'"conversationId":\s*"([a-f0-9\-]+)"', tool_result)
                    if m:
                        sub_conv_id = m.group(1)
                        sub_ctx = detect_startupos_context(text=pending_sub_prompt)
                        sub_feat = sub_ctx.get("feature") or active_feature
                        sub_stg = sub_ctx.get("stage") or active_stage

                        state.setdefault("subagents", {})[sub_conv_id] = {
                            "parent_conv_id": conv_id,
                            "session_id": session_id,
                            "turn_trace_id": turn_trace_id,
                            "turn_step": turn_step,
                            "role": pending_sub_role or "subagent",
                            "prompt": pending_sub_prompt,
                            "model": pending_sub_model or model_name,
                            "feature": sub_feat,
                            "stage": sub_stg
                        }

                try:
                    span_obs = client.start_observation(
                        trace_context={"trace_id": turn_trace_id},
                        name="tool-result",
                        as_type="span",
                        output=tool_result[:5000] if isinstance(tool_result, str) else tool_result,
                        status_message=status if status != "DONE" else None,
                        level="ERROR" if status == "ERROR" else "DEFAULT",
                        metadata={
                            "step_index": idx,
                            "turn_step": turn_step,
                            "conversation_id": conv_id,
                            "session_id": session_id
                        }
                    )
                    span_obs.end()
                except Exception:
                    pass

        if idx > max_step_synced:
            max_step_synced = idx

    state[conv_id] = max_step_synced

    # 3. Sincroniza quaisquer subagentes associados a esta conversa
    subagents_map = state.get("subagents", {})
    for sub_id, sub_info in list(subagents_map.items()):
        if sub_info.get("parent_conv_id") == conv_id:
            try:
                sync_subagent(client, sub_id, sub_info, state, user_id, parent_model=normalized_model, skills_map=skills_map)
            except Exception:
                pass

    try:
        client.flush()
    except Exception:
        pass

    save_state(state)
    print(json.dumps(output))

if __name__ == "__main__":
    main()
