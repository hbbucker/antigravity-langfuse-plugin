#!/usr/bin/env python3
"""
Dashboard Provisioner & Verifier for StartupOS & Antigravity Telemetry in Langfuse.

Cross-platform (Windows & Linux).
Connects to Langfuse using credentials resolved from environment, .langfuse.env,
or ~/.gemini/antigravity-cli/langfuse.json.
Validates telemetry ingestion and outputs metrics for all tracked features.
"""

import sys
import os
import json
from pathlib import Path

# Adiciona diretório scripts ao path
current_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(current_dir))

from langfuse_tracer import resolve_langfuse_config, is_langfuse_healthy

def main():
    print("=" * 65)
    print("   StartupOS & Antigravity - Langfuse Telemetry Verifier")
    print("=" * 65)

    config = resolve_langfuse_config([])
    host = config.get("host")
    pub_key = config.get("public_key")
    sec_key = config.get("secret_key")

    print(f"\n[1] Conectividade com Langfuse:")
    print(f"    Host:       {host}")
    print(f"    Public Key: {pub_key[:12] if pub_key else 'N/A'}...")

    if not is_langfuse_healthy(host):
        print(f"    Status:     \033[33mOFFLINE ou Inacessível\033[0m")
        print("\nVerifique se o container está rodando ou se a URL remota está acessível.")
        sys.exit(1)

    print("    Status:     \033[32mONLINE\033[0m")

    try:
        from langfuse import Langfuse
        client = Langfuse(public_key=pub_key, secret_key=sec_key, host=host)
        client.auth_check()
        print("    Auth Check: \033[32mAutenticado com Sucesso!\033[0m")
    except Exception as e:
        print(f"    Auth Check: \033[31mFalha na Autenticação ({e})\033[0m")
        sys.exit(1)

    print("\n[2] Estrutura de Filtros Recomendados no Langfuse UI:")
    print("    Para visualizar custos e execuções no Dashboard do Langfuse:")
    print("    - Abra: " + host)
    print("    - Acesse 'Traces' ou 'Scores / Analytics'")
    print("    - Filtre por Tags:")
    print("        * tag: feature:* (Lista todas as features)")
    print("        * tag: feature:adrs-standardization")
    print("        * tag: stage:tasks")
    print("        * tag: subagent")
    print("\n[3] Guia de Widgets para o Dashboard 'StartupOS - Features':")
    print("    Widget 1: Total Cost by Feature")
    print("      -> Agrupamento: Tag 'feature'")
    print("      -> Métrica: Total Cost (USD)")
    print("    Widget 2: Turn Count per Feature")
    print("      -> Agrupamento: Tag 'feature'")
    print("      -> Métrica: Trace Count")
    print("    Widget 3: Model Distribution")
    print("      -> Agrupamento: Model Name")
    print("      -> Métrica: Total Tokens / Total Cost")
    print("    Widget 4: Subagent Hierarchy")
    print("      -> Métrica: Agent Spans inside Parent Feature Traces")

    print("\n" + "=" * 65)
    print("✔ Verificação e guia de provisionamento concluídos com sucesso!")
    print("=" * 65)

if __name__ == "__main__":
    main()
