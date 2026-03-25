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
        self.rotate(45, 100, 150)
        self.text(30, 190, 'C O N F I D E N C I A L')
        self.rotate(0)

# --- FUNÇÕES DE CÁLCULO ---
def format_brl(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def gerar_lista_meses(data_inicio, horizonte):
    meses = []
    for i in range(horizonte):
        # Correção para não pular meses: adicionamos i meses à data inicial
        target_date = (data_inicio.replace(day=1) + timedelta(days=i*32)).replace(day=1)
        meses.append(target_date.strftime("%b. de %y").lower())
    return meses

# --- INTERFACE PRINCIPAL ---
st.set_page_config(page_title="PMO Impact Analysis", layout="wide")
local_css()

# Cabeçalho do Print 1
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
    st.button("🧹 Limpar Dados", on_click=lambda: db_conn.execute("DELETE FROM matriz_alocacao"))

# 1. INFORMAÇÕES DO PROJETO (Print 2)
st.markdown('<div class="section-header">🏢 Informações do Projeto</div>', unsafe_allow_html=True)
with st.container(border=True):
    c1, c2 = st.columns(2)
    nome_proj = c1.text_input("NOME DO PROJETO", value="Einstein")
    gp_resp = c2.text_input("RESPONSÁVEL (GP)", value="Kamyla")
    justificativa = st.text_area("JUSTIFICATIVA DA MUDANÇA / CONTEXTO", value="Rollout do ACS")

# 2. CENÁRIOS DE MUDANÇA (Prints 8, 9, 10, 11)
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

with cenarios[1]:
    # Estrutura para Retrabalho conforme print 9
    st.write("Configuração de Retrabalho por Item/Esforço")

# 3. MATRIZ DE ALOCAÇÃO (Print 3 & 12)
st.markdown('<div class="section-header">1. Matriz de Alocação & Orçamento</div>', unsafe_allow_html=True)
with st.container(border=True):
    m_col1, m_col2, m_col3 = st.columns([1, 1, 1])
    data_inicio = m_col1.date_input("INÍCIO DO EVENTO/IMPACTO", value=datetime(2026, 1, 19))
    horizonte = m_col2.number_input("MESES (HORIZONTE)", min_value=1, value=4)
    
    lista_meses = gerar_lista_meses(data_inicio, horizonte)

    # Área de Adição (Estilo Print 3)
    with st.expander("ADICIONAR RECURSO AO ORÇAMENTO", expanded=True):
        f1, f2, f3, f4, f5, f6 = st.columns([2, 2, 1.5, 1.5, 1.5, 1])
        cargo = f1.selectbox("CARGO", ["Consultor", "Gerente", "Analista", "Arquiteto"])
        nivel = f2.selectbox("NÍVEL", ["Junior", "Pleno", "Senior", "N/A"])
        reg = f3.text_input("REGIONAL/CC", value="N/A")
        taxa_h = f4.number_input("TAXA/HORA (R$)", value=27.70)
        hrs_base = f5.number_input("HRS/MÊS (BASE)", value=160)
        if f6.button("+ ADICIONAR"):
            # Mock de distribuição de horas
            h_dist = {m: hrs_base for m in lista_meses}
            total_r = sum(h_dist.values()) * taxa_h
            db_conn.execute("INSERT INTO matriz_alocacao (projeto, cargo, nivel, reg, taxa, horas_json, total) VALUES (?,?,?,?,?,?,?)",
                         (nome_proj, cargo, nivel, reg, taxa_h, str(h_dist), total_r))
            db_conn.commit()
            st.rerun()

    # Tabela de Matriz
    df_matriz = pd.read_sql_query(f"SELECT * FROM matriz_alocacao WHERE projeto='{nome_proj}'", db_conn)
    if not df_matriz.empty:
        display_data = []
        for _, row in df_matriz.iterrows():
            h_dict = eval(row['horas_json'])
            r_line = {
                "CARGO": row['cargo'], "NÍVEL": row['nivel'], 
                "REG.": row['reg'], "TAXA": row['taxa']
            }
            for m in lista_meses:
                r_line[m.upper()] = h_dict.get(m, 0)
            r_line["TOTAL"] = format_brl(row['total'])
            display_data.append(r_line)
        
        st.table(pd.DataFrame(display_data))

# 4. RESUMO FINANCEIRO (Print 4 & 13)
st.markdown('<div class="section-header">📊 Impacto Mensal na Margem do Projeto</div>', unsafe_allow_html=True)
custo_total_matriz = df_matriz['total'].sum() if not df_matriz.empty else 0.0

c_res1, c_res2, c_res3 = st.columns(3)
c_res1.markdown(f"""<div class="stMetric"><small>Custo Estimado (Baseline)</small><br><b>{format_brl(custo_total_matriz)}</b><br><small style="color:gray;">Sem Risco</small></div>""", unsafe_allow_html=True)
c_res2.markdown(f"""<div class="stMetric" style="border-top-color: #fbc02d;"><small>Reserva de Risco (Adicional)</small><br><b style="color:#d32f2f;">-{format_brl(custo_total_matriz * 0.42)}</b><br><small class="delta-pert">+ Delta PERT</small></div>""", unsafe_allow_html=True)
c_res3.markdown(f"""<div class="stMetric" style="border-top-color: #7e57c2;"><small>Orçamento Total Cenário</small><br><b style="color:#1a237e;">{format_brl(custo_total_matriz)}</b><br><small style="color:gray;">Base + Risco (95%)</small></div>""", unsafe_allow_html=True)

# 5. DRE E GRÁFICOS (Print 6 & 15)
st.markdown('<div class="section-header">📉 DRE do Projeto: Análise de Margem Final</div>', unsafe_allow_html=True)
with st.container(border=True):
    col_d1, col_d2, col_d3 = st.columns(3)
    margem_meta = col_d1.number_input("MARGEM INICIAL (META) %", value=31.0)
    receita_liq = col_d2.number_input("RECEITA LÍQUIDA ATUAL", value=4719147.0)
    custo_eac = col_d3.number_input("CUSTO TOTAL ATUAL (EAC)", value=4963246.0)
    
    # Cálculos de Erosão
    margem_atual = (1 - (custo_eac/receita_liq)) * 100
    novo_eac = custo_eac + custo_total_matriz
    margem_projetada = (1 - (novo_eac/receita_liq)) * 100
    erosao = margem_atual - margem_projetada

    d_res1, d_res2, d_res3 = st.columns(3)
    d_res1.metric("MARGEM ATUAL", f"{margem_atual:.1f}%", help="Antes do Evento")
    d_res2.metric("PROJETADA (MÉDIA)", f"{margem_projetada:.1f}%", delta=f"-{erosao:.1f} p.p.", delta_color="inverse")
    d_res3.markdown(f"""<div style="text-align:center; padding:10px; background:#fff5f5; border-radius:20px; color:#c62828; border:1px solid #ef9a9a;">Erosão de Margem: {erosao:.1f} p.p.</div>""", unsafe_allow_html=True)

# GRÁFICO TRIÂNGULO DE FERRO (Print 5)
st.markdown("---")
col_g1, col_g2 = st.columns(2)

with col_g1:
    st.write("**Análise Integrada: Prazo & Triângulo**")
    categories = ['Custo', 'Prazo', 'Escopo']
    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(r=[80, 70, 90, 80], theta=categories+['Custo'], fill='toself', name='Planejado'))
    fig_radar.add_trace(go.Scatterpolar(r=[100, 95, 95, 100], theta=categories+['Custo'], fill='toself', name='Projetado (Impacto)'))
    fig_radar.update_layout(polar=dict(radialaxis=dict(visible=False)), showlegend=True, height=350)
    st.plotly_chart(fig_radar, use_container_width=True)

with col_g2:
    st.write("**Histograma de Erosão (Recursos vs Custo)**")
    # Histograma solicitado
    df_hist = pd.DataFrame({
        'Categoria': ['Baseline', 'Impacto Real', 'Risco'],
        'Valor': [custo_eac, custo_total_matriz, custo_total_matriz*0.3]
    })
    fig_hist = px.bar(df_hist, x='Categoria', y='Valor', color='Categoria', 
                     color_manual={'Baseline':'#455a64', 'Impacto Real':'#d32f2f', 'Risco':'#fbc02d'})
    st.plotly_chart(fig_hist, use_container_width=True)

# GERAÇÃO DO PDF EXECUTIVO
if st.sidebar.button("📊 GERAR RELATÓRIO PDF"):
    pdf = RelatorioExecutivo()
    pdf.add_page()
    pdf.add_watermark()
    
    # Seção 1
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, " 1. INFORMAÇÕES DO PROGRAMA", 0, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f"Programa: {nome_proj} | GP: {gp_resp}", 0, 1)
    pdf.multi_cell(0, 8, f"Justificativa: {justificativa}")
    
    # Seção 2 - Matriz
    pdf.ln(5)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, " 2. MATRIZ DE ALOCAÇÃO ADICIONAL", 0, 1, 'L', fill=True)
    pdf.set_font('Arial', 'B', 9)
    # Cabeçalho da tabela no PDF
    pdf.cell(40, 8, "Cargo", 1); pdf.cell(30, 8, "Nivel", 1); pdf.cell(40, 8, "Taxa", 1); pdf.cell(40, 8, "Total", 1, 1)
    pdf.set_font('Arial', '', 9)
    for _, r in df_matriz.iterrows():
        pdf.cell(40, 8, r['cargo'], 1)
        pdf.cell(30, 8, r['nivel'], 1)
        pdf.cell(40, 8, f"R$ {r['taxa']}", 1)
        pdf.cell(40, 8, format_brl(r['total']), 1, 1)
    
    # Inclusão de Gráficos no PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
        fig_radar.write_image(tmpfile.name)
        pdf.ln(10)
        pdf.image(tmpfile.name, x=10, y=pdf.get_y(), w=90)
        
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile2:
        fig_hist.write_image(tmpfile2.name)
        pdf.image(tmpfile2.name, x=110, y=pdf.get_y(), w=90)

    pdf.ln(70)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, " 3. PARECER DE MARGEM E EROSÃO", 0, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 10, f"Margem Baseline: {margem_atual:.2f}%", 0, 1)
    pdf.set_text_color(200, 0, 0)
    pdf.cell(0, 10, f"Margem Projetada com Impacto: {margem_projetada:.2f}%", 0, 1)
    pdf.cell(0, 10, f"Erosão Financeira Total: {format_brl(custo_total_matriz)}", 0, 1)

    html_pdf = pdf.output(dest='S')
    st.sidebar.download_button("📥 Baixar PDF Validado", data=bytes(html_pdf), file_name=f"Relatorio_Impacto_{nome_proj}.pdf")
