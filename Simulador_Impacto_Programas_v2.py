import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from fpdf import FPDF
from datetime import datetime
from dateutil.relativedelta import relativedelta
import tempfile
import os

# --- ESTILO EXECUTIVO ---
def local_css():
    st.markdown("""
    <style>
        .main { background-color: #f8f9fa; }
        .stMetric { background-color: white; padding: 20px; border-radius: 10px; border-top: 4px solid #003366; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
        .header-box { background-color: white; padding: 25px; border-radius: 12px; border-left: 10px solid #003366; margin-bottom: 25px; }
        .section-header { color: #003366; font-weight: bold; margin-top: 25px; border-bottom: 2px solid #00bfa5; padding-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- ENGINE DE DADOS ---
def init_db():
    conn = sqlite3.connect('pmo_enterprise_v3.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS matriz_alocacao 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, projeto TEXT, cargo TEXT, nivel TEXT, 
                  reg TEXT, taxa REAL, horas_json TEXT, total REAL)''')
    conn.commit()
    return conn

db_conn = init_db()

# --- CLASSE PDF DE ALTA FIDELIDADE ---
class RelatorioExecutivo(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 10)
        self.set_text_color(150)
        self.cell(0, 10, 'ESTRITAMENTE CONFIDENCIAL | DIRETORIA DE OPERACOES', 0, 1, 'R')
        self.line(10, 20, 200, 20)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()} | Dossie de Impacto Financeiro', 0, 0, 'C')

    def watermark(self):
        self.set_font('Arial', 'B', 50)
        self.set_text_color(245, 245, 245)
        self.rotate(45, 100, 150)
        self.text(40, 190, 'C O N F I D E N C I A L')
        self.rotate(0)

def format_brl(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def gerar_lista_meses(data_inicio, horizonte):
    return [(data_inicio + relativedelta(months=i)).strftime("%b/%y").lower() for i in range(horizonte)]

# --- INTERFACE ---
st.set_page_config(page_title="PMO Intelligence Pro", layout="wide")
local_css()
st.markdown('<div class="header-box"><h1 style="color:#003366;margin:0;">Simulador de Impacto e Erosão de Margem</h1><p style="color:#666;margin:0;">Ecossistema de Desenvolvimento de Sistemas</p></div>', unsafe_allow_html=True)

# 1. SETUP
col_s1, col_s2, col_s3 = st.columns([2, 1, 1])
nome_proj = col_s1.text_input("NOME DO PROGRAMA", value="Einstein - ACS")
data_inicio = col_s2.date_input("INÍCIO DO EVENTO", value=datetime(2026, 1, 19))
horizonte = col_s3.number_input("MESES (HORIZONTE)", min_value=1, value=4)
lista_meses = gerar_lista_meses(data_inicio, horizonte)

# 2. MATRIZ DE ALOCAÇÃO (CRUD MELHORADO)
st.markdown('<div class="section-header">1. Matriz de Alocação e Orçamento Adicional</div>', unsafe_allow_html=True)
with st.container(border=True):
    f1, f2, f3, f4, f5 = st.columns([2, 1, 1, 1, 1])
    cargo = f1.selectbox("CARGO", ["Consultor Senior", "Arquiteto", "Analista Pleno", "Gerente"])
    reg = f2.text_input("REGIONAL", value="Matriz")
    taxa_h = f3.number_input("TAXA/HORA", value=185.0)
    hrs_base = f4.number_input("HRS/MÊS", value=160)
    
    if f5.button("➕ ADICIONAR"):
        h_dist = {m: hrs_base for m in lista_meses}
        total_r = sum(h_dist.values()) * taxa_h
        db_conn.execute("INSERT INTO matriz_alocacao (projeto, cargo, nivel, reg, taxa, horas_json, total) VALUES (?,?,?,?,?,?,?)",
                     (nome_proj, cargo, "Senior", reg, taxa_h, str(h_dist), total_r))
        db_conn.commit()
        st.rerun()

    df_db = pd.read_sql_query(f"SELECT * FROM matriz_alocacao WHERE projeto='{nome_proj}'", db_conn)
    if not df_db.empty:
        for idx, row in df_db.iterrows():
            c_row = st.columns([4, 2, 2, 1])
            c_row[0].write(f"**{row['cargo']}** | {row['reg']}")
            c_row[1].write(format_brl(row['taxa']) + " /h")
            c_row[2].write("**Total:** " + format_brl(row['total']))
            if c_row[3].button("🗑️", key=f"del_{row['id']}"):
                db_conn.execute(f"DELETE FROM matriz_alocacao WHERE id={row['id']}")
                db_conn.commit()
                st.rerun()
    custo_total_adicional = df_db['total'].sum() if not df_db.empty else 0.0

# 3. DRE E ANÁLISE DE MARGEM
st.markdown('<div class="section-header">2. Análise de DRE e Impacto Financeiro</div>', unsafe_allow_html=True)
c_dre1, c_dre2, c_dre3 = st.columns(3)
receita_liq = c_dre1.number_input("RECEITA LÍQUIDA ATUAL", value=5000000.0)
custo_eac_atual = c_dre2.number_input("CUSTO EAC ATUAL", value=3200000.0)
margem_meta = c_dre3.number_input("MARGEM META %", value=35.0)

margem_atual = (1 - (custo_eac_atual / receita_liq)) * 100
novo_eac = custo_eac_atual + custo_total_adicional
nova_margem = (1 - (novo_eac / receita_liq)) * 100
erosao = margem_atual - nova_margem

st.divider()
m1, m2, m3 = st.columns(3)
m1.metric("MARGEM ATUAL", f"{margem_atual:.1f}%")
m2.metric("MARGEM PROJETADA", f"{nova_margem:.1f}%", delta=f"-{erosao:.1f} p.p.", delta_color="inverse")
m3.metric("VALOR DO IMPACTO", format_brl(custo_total_adicional))

# 4. GRÁFICOS (CORRIGIDOS)
col_g1, col_g2 = st.columns(2)
with col_g1:
    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(r=[1, 1, 1, 1], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Planejado'))
    fig_radar.add_trace(go.Scatterpolar(r=[1.5, 1.4, 1.2, 1.5], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Impacto'))
    fig_radar.update_layout(title="Desvio do Triângulo de Ferro", polar=dict(radialaxis=dict(visible=False)))
    st.plotly_chart(fig_radar, use_container_width=True)

with col_g2:
    df_hist = pd.DataFrame({
        'Categoria': ['Baseline', 'Impacto Real', 'Risco P95'],
        'Valor': [custo_eac_atual, custo_total_adicional, custo_total_adicional * 0.42]
    })
    # CORREÇÃO AQUI: color_discrete_map
    fig_hist = px.bar(df_hist, x='Categoria', y='Valor', color='Categoria',
                     title="Histograma de Erosão de Custos",
                     color_discrete_map={'Baseline':'#455a64', 'Impacto Real':'#d32f2f', 'Risco P95':'#fbc02d'})
    st.plotly_chart(fig_hist, use_container_width=True)

# 5. GERAÇÃO DO PDF EXECUTIVO
if st.sidebar.button("📊 GERAR DOSSIÊ COMPLETO"):
    pdf = RelatorioExecutivo()
    pdf.add_page()
    pdf.watermark()
    
    # Cabeçalho
    pdf.set_fill_color(0, 51, 102)
    pdf.set_text_color(255)
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 12, f" DOSSIE EXECUTIVO: {nome_proj.upper()}", 0, 1, 'L', fill=True)
    
    # Resumo
    pdf.ln(5)
    pdf.set_text_color(0)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 10, "1. RESUMO DA ANALISE", 0, 1)
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 8, f"Este documento apresenta o impacto financeiro projetado para o programa. "
                         f"A analise aponta uma erosao de margem de {erosao:.2f} pontos percentuais, "
                         f"elevando o custo total para {format_brl(novo_eac)}.")

    # Gráficos
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as t1, \
         tempfile.NamedTemporaryFile(delete=False, suffix=".png") as t2:
        fig_radar.write_image(t1.name)
        fig_hist.write_image(t2.name)
        pdf.image(t1.name, x=10, y=70, w=90)
        pdf.image(t2.name, x=105, y=70, w=90)
    
    # Tabela de Custos
    pdf.set_y(140)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 10, "2. DETALHAMENTO DA MATRIZ DE IMPACTO", 0, 1)
    pdf.set_font('Arial', 'B', 9)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(70, 8, "Cargo", 1, 0, 'C', True)
    pdf.cell(60, 8, "Regional", 1, 0, 'C', True)
    pdf.cell(55, 8, "Impacto Financeiro", 1, 1, 'C', True)
    
    pdf.set_font('Arial', '', 9)
    for _, r in df_db.iterrows():
        pdf.cell(70, 8, r['cargo'], 1)
        pdf.cell(60, 8, r['reg'], 1)
        pdf.cell(55, 8, format_brl(r['total']), 1, 1)

    # Conclusão
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 12)
    pdf.set_text_color(200, 0, 0)
    pdf.cell(0, 10, f"MARGEM FINAL PROJETADA: {nova_margem:.2f}%", 0, 1, 'C')

    output = pdf.output(dest='S')
    st.sidebar.download_button("📥 Baixar Dossiê Validado", data=bytes(output), file_name=f"Dossie_{nome_proj}.pdf")
