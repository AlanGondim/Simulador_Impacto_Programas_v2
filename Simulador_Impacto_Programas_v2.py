import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from fpdf import FPDF
from datetime import datetime, timedelta
import tempfile
import os

# --- CONFIGURAÇÕES DE INTERFACE (ESTILO EXECUTIVO) ---
def local_css():
    st.markdown("""
    <style>
        .main { background-color: #f4f7f6; }
        .stMetric { background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-top: 4px solid #00bfa5; }
        .header-box { background-color: white; padding: 25px; border-radius: 12px; border-left: 8px solid #003366; margin-bottom: 25px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .section-header { color: #003366; font-weight: bold; margin-top: 25px; margin-bottom: 15px; font-size: 1.4rem; display: flex; align-items: center; }
        .card-impacto { background: white; padding: 20px; border-radius: 10px; border: 1px solid #e0e0e0; }
        .delta-pert { color: #b8860b; font-weight: bold; font-size: 0.9em; }
    </style>
    """, unsafe_allow_html=True)

# --- ENGINE DE DADOS ---
def init_db():
    conn = sqlite3.connect('pmo_enterprise_v2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS matriz_alocacao 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, projeto TEXT, cargo TEXT, nivel TEXT, 
                  reg TEXT, taxa REAL, horas_json TEXT, total REAL)''')
    conn.commit()
    return conn

db_conn = init_db()

# --- CLASSE PDF PROFISSIONAL COM GRÁFICOS ---
class RelatorioExecutivo(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'RELATÓRIO PMO - ANÁLISE DE IMPACTO (ESTRITAMENTE CONFIDENCIAL)', 0, 1, 'R')
        self.line(10, 20, 200, 20)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Página {self.page_no()} | Diretoria de Operações - MV', 0, 0, 'C')

    def add_watermark(self):
        self.set_font('Arial', 'B', 40)
        self.set_text_color(240, 240, 240)
        # Salva o estado atual para rotação
        with self.rotation(45, 100, 150):
            self.text(30, 190, 'C O N F I D E N C I A L')

# --- FUNÇÕES DE CÁLCULO ---
def format_brl(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def gerar_lista_meses(data_inicio, horizonte):
    meses = []
    for i in range(horizonte):
        target_date = (data_inicio.replace(day=1) + timedelta(days=i*31)).replace(day=1)
        meses.append(target_date.strftime("%b. de %y").lower())
    return meses

# --- INTERFACE PRINCIPAL ---
st.set_page_config(page_title="PMO Impact Analysis", layout="wide")
local_css()

col_h1, col_h2 = st.columns([0.7, 0.3])
with col_h1:
    st.markdown(f"""
    <div class="header-box">
        <h1 style="margin:0; color:#1a237e;">Relatório PMO - Análise de Impacto</h1>
        <p style="margin:0; color:#546e7a; font-size:1.1rem;">Estimativa Paramétrica, Matriz de Alocação e Análise de DRE</p>
    </div>
    """, unsafe_allow_html=True)
with col_h2:
    st.write("")
    if st.button("🧹 Limpar Todos os Dados"):
        db_conn.execute("DELETE FROM matriz_alocacao")
        db_conn.commit()
        st.rerun()

# 1. INFORMAÇÕES DO PROJETO
st.markdown('<div class="section-header">🏢 Informações do Projeto</div>', unsafe_allow_html=True)
with st.container(border=True):
    c1, c2 = st.columns(2)
    nome_proj = c1.text_input("NOME DO PROJETO", value=" ")
    gp_resp = c2.text_input("RESPONSÁVEL (GP)", value=" ")
    justificativa = st.text_area("JUSTIFICATIVA DA MUDANÇA / CONTEXTO", value=" ")

# 2. CENÁRIOS DE MUDANÇA
st.markdown('<div class="section-header">🚀 Cenários da Mudança</div>', unsafe_allow_html=True)
cenarios = st.tabs(["Rollout", "Retrabalho", "Bugs", "Infraestrutura"])

with cenarios[0]:
    col_r1, col_r2 = st.columns(2)
    escopo_rest = col_r1.number_input("ESCOPO RESTANTE (QTD. ROLLOUTS)", value=11)
    baseline_vel = col_r2.number_input("BASELINE (VEL.)", value=5.5)
    st.markdown("---")
    st.write("**ESTIMATIVA DE VELOCIDADE (ROLLOUTS/MÊS)**")
    v1, v2, v3 = st.columns(3)
    v_otm = v1.number_input("OTIMISTA", value=6.0, key="v_otm")
    v_pro = v2.number_input("PROVÁVEL", value=6.0, key="v_pro")
    v_pes = v3.number_input("PESSIMISTA", value=4.0, key="v_pes")
    vel_pert = (v_otm + 4*v_pro + v_pes) / 6

# 3. MATRIZ DE ALOCAÇÃO
st.markdown('<div class="section-header">1. Matriz de Alocação & Orçamento</div>', unsafe_allow_html=True)
with st.container(border=True):
    m_col1, m_col2, m_col3 = st.columns([1, 1, 1])
    data_inicio = m_col1.date_input("INÍCIO DO EVENTO/IMPACTO", value=datetime(2026, 1, 19))
    horizonte = m_col2.number_input("MESES (HORIZONTE)", min_value=1, value=1)
    lista_meses = gerar_lista_meses(data_inicio, horizonte)

    with st.expander("ADICIONAR RECURSO AO ORÇAMENTO", expanded=True):
        f1, f2, f3, f4, f5, f6 = st.columns([2, 2, 1.5, 1.5, 1.5, 1])
        cargo_add = f1.selectbox("CARGO", ["Consultor", "Gerente", "Analista", "Desenvolvedor"])
        nivel_add = f2.selectbox("NÍVEL", ["Junior", "Pleno", "Senior", "N/A"])
        reg_add = f3.text_input("REGIONAL/CC", value="N/A")
        taxa_h_add = f4.number_input("TAXA/HORA (R$)", value=150.0)
        hrs_base_add = f5.number_input("HRS/MÊS (BASE)", value=160)
        if f6.button("+ ADICIONAR"):
            h_dist = {m: hrs_base_add for m in lista_meses}
            total_r = sum(h_dist.values()) * taxa_h_add
            db_conn.execute("INSERT INTO matriz_alocacao (projeto, cargo, nivel, reg, taxa, horas_json, total) VALUES (?,?,?,?,?,?,?)",
                         (nome_proj, cargo_add, nivel_add, reg_add, taxa_h_add, str(h_dist), total_r))
            db_conn.commit()
            st.rerun()

    df_matriz = pd.read_sql_query(f"SELECT * FROM matriz_alocacao WHERE projeto='{nome_proj}'", db_conn)
    if not df_matriz.empty:
        for idx, row in df_matriz.iterrows():
            col_res = st.columns([3, 2, 2, 2, 1])
            col_res[0].write(f"**{row['cargo']}** ({row['nivel']})")
            col_res[1].write(f"Reg: {row['reg']}")
            col_res[2].write(f"Taxa: {format_brl(row['taxa'])}")
            col_res[3].write(f"**Total: {format_brl(row['total'])}**")
            if col_res[4].button("🗑️", key=f"del_{row['id']}"):
                db_conn.execute(f"DELETE FROM matriz_alocacao WHERE id={row['id']}")
                db_conn.commit()
                st.rerun()

# 4. DRE E GRÁFICOS
st.markdown('<div class="section-header">📊 Análise de Margem e Impacto Financeiro</div>', unsafe_allow_html=True)
custo_total_matriz = df_matriz['total'].sum() if not df_matriz.empty else 0.0

with st.container(border=True):
    col_d1, col_d2, col_d3 = st.columns(3)
    receita_liq = col_d1.number_input("RECEITA LÍQUIDA ATUAL", value=1000.0)
    custo_eac = col_d2.number_input("CUSTO TOTAL ATUAL (EAC)", value=1000.0)
    
    margem_atual = (1 - (custo_eac/receita_liq)) * 100
    novo_eac = custo_eac + custo_total_matriz
    margem_projetada = (1 - (novo_eac/receita_liq)) * 100
    erosao = margem_atual - margem_projetada

    d_res1, d_res2, d_res3 = st.columns(3)
    d_res1.metric("MARGEM ATUAL", f"{margem_atual:.1f}%")
    d_res2.metric("PROJETADA", f"{margem_projetada:.1f}%", delta=f"-{erosao:.1f} p.p.", delta_color="inverse")
    d_res3.markdown(f"""<div style="text-align:center; padding:10px; background:#fff5f5; border-radius:10px; color:#c62828; border:1px solid #ef9a9a;">Erosão: {format_brl(custo_total_matriz)}</div>""", unsafe_allow_html=True)

col_g1, col_g2 = st.columns(2)
with col_g1:
    categories = ['Custo', 'Prazo', 'Escopo']
    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(r=[80, 70, 90, 80], theta=categories+['Custo'], fill='toself', name='Baseline'))
    fig_radar.add_trace(go.Scatterpolar(r=[100, 95, 95, 100], theta=categories+['Custo'], fill='toself', name='Impacto'))
    fig_radar.update_layout(polar=dict(radialaxis=dict(visible=False)), height=350, title="Triângulo de Ferro")
    st.plotly_chart(fig_radar, use_container_width=True)

with col_g2:
    df_hist = pd.DataFrame({
        'Categoria': ['Baseline', 'Impacto Real', 'Risco'],
        'Valor': [custo_eac, custo_total_matriz, custo_total_matriz*0.3]
    })
    # CORREÇÃO DO ERRO: color_discrete_map em vez de color_manual
    fig_hist = px.bar(df_hist, x='Categoria', y='Valor', color='Categoria',
                     color_discrete_map={'Baseline':'#455a64', 'Impacto Real':'#d32f2f', 'Risco':'#fbc02d'})
    fig_hist.update_layout(height=350, title="Histograma de Custos")
    st.plotly_chart(fig_hist, use_container_width=True)

# --- NOVO BLOCO DE GERAÇÃO DO PDF (CORRIGIDO) ---
if st.sidebar.button("📊 GERAR DOSSIÊ COMPLETO"):
    pdf = RelatorioExecutivo()
    pdf.add_page()
    pdf.add_watermark()
    
    # 1. Informações do Programa
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, " 1. INFORMACOES DO PROGRAMA", 0, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f"Programa: {nome_proj} | GP: {gp_resp}", 0, 1)
    pdf.multi_cell(0, 8, f"Justificativa: {justificativa.encode('latin-1', 'ignore').decode('latin-1')}")
    
    # 2. Matriz de Alocação
    pdf.ln(5)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, " 2. MATRIZ DE ALOCACAO ADICIONAL", 0, 1, 'L', fill=True)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(50, 8, "Cargo", 1); pdf.cell(40, 8, "Regiao", 1); pdf.cell(50, 8, "Impacto Financeiro", 1, 1)
    pdf.set_font('Arial', '', 9)
    for _, r in df_matriz.iterrows():
        pdf.cell(50, 8, r['cargo'], 1)
        pdf.cell(40, 8, r['reg'], 1)
        pdf.cell(50, 8, format_brl(r['total']), 1, 1)
    
    # 3. Inclusão de Gráficos (USANDO ENGINE 'JSON' OU BYTES PARA EVITAR KALEIDO)
    # Tentamos converter para imagem. Se o Kaleido falhar, avisamos o usuário.
    try:
        pdf.ln(10)
        curr_y = pdf.get_y()
        
        # Gerar imagens como bytes primeiro (contorno para o erro de 'tabs')
        img_radar_bytes = fig_radar.to_image(format="png", width=600, height=450, engine="kaleido")
        img_hist_bytes = fig_hist.to_image(format="png", width=600, height=450, engine="kaleido")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp1:
            tmp1.write(img_radar_bytes)
            pdf.image(tmp1.name, x=10, y=curr_y, w=90)
            
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp2:
            tmp2.write(img_hist_bytes)
            pdf.image(tmp2.name, x=105, y=curr_y, w=90)
            
        pdf.ln(70) # Espaço para os gráficos
    except Exception as e:
        pdf.ln(10)
        pdf.set_text_color(255, 0, 0)
        pdf.cell(0, 10, "Erro ao renderizar graficos. Verifique a instalacao do Kaleido.", 0, 1)
        pdf.set_text_color(0, 0, 0)

    # 4. Parecer de Margem
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, " 3. PARECER DE MARGEM E EROSAO", 0, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 8, f"Margem Baseline: {margem_atual:.2f}%", 0, 1)
    pdf.set_text_color(200, 0, 0)
    pdf.cell(0, 8, f"Margem Projetada: {margem_projetada:.2f}%", 0, 1)
    pdf.cell(0, 8, f"Custo Incremental Total: {format_brl(custo_total_matriz)}", 0, 1)

    pdf_bytes = pdf.output(dest='S')
    st.sidebar.download_button("📥 Baixar Dossie Validado", data=bytes(pdf_bytes), file_name=f"Dossie_Impacto_{nome_proj}.pdf")
