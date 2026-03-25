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
import json

# --- CONFIGURAÇÕES DE INTERFACE ---
def local_css():
    st.markdown("""
    <style>
        .main { background-color: #f8f9fa; }
        .stMetric { background-color: white; padding: 15px; border-radius: 8px; border-top: 4px solid #003366; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .header-box { background-color: white; padding: 20px; border-radius: 10px; border-left: 10px solid #003366; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .section-header { color: #003366; font-weight: bold; margin-top: 30px; border-bottom: 2px solid #e0e0e0; padding-bottom: 5px; font-size: 1.2rem; }
        .sidebar .sidebar-content { background-image: linear-gradient(#2e7d32,#2e7d32); color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- ENGINE DE DADOS ---
def init_db():
    conn = sqlite3.connect('pmo_elite_v2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS matriz_alocacao 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, projeto TEXT, cargo TEXT, nivel TEXT, 
                  reg TEXT, taxa REAL, horas_json TEXT, total REAL)''')
    conn.commit()
    return conn

db_conn = init_db()

# --- CLASSE PDF PROFISSIONAL ---
class RelatorioElite(FPDF):
    def header(self):
        # Correção 0.0 e 0.1: Removido o "R" extra e ajustado conforme print
        self.set_font('Arial', 'B', 14)
        self.set_text_color(0, 51, 102)
        # Ícone de relatório (simulado com texto/forma)
        self.rect(10, 10, 6, 8, 'F') 
        self.set_x(18)
        self.cell(0, 10, 'Relatorio PMO PROGRAMAS - Analise de Impacto Financeiro', 0, 1, 'L')
        self.set_draw_color(0, 51, 102)
        self.line(10, 22, 200, 22)
        self.ln(5)

    def footer(self):
        self.set_y(-30)
        self.set_font('Arial', 'B', 8)
        self.set_draw_color(180, 180, 180)
        self.line(20, self.get_y(), 80, self.get_y())
        self.line(130, self.get_y(), 190, self.get_y())
        self.cell(90, 10, 'Diretor de Operacoes', 0, 0, 'C')
        self.cell(90, 10, 'Gerencia de Operacoes', 0, 1, 'C')
        self.set_y(-15)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 10, f'Pagina {self.page_no()} | CONFIDENCIAL - PMO PROGRAMAS', 0, 0, 'C')

    def add_watermark(self):
        self.set_font('Arial', 'B', 45)
        self.set_text_color(245, 245, 245)
        with self.rotation(45, 100, 150):
            self.text(40, 190, 'C O N F I D E N C I A L')

# --- FUNÇÕES DE SUPORTE ---
def format_brl(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_meses_list(start_date, months):
    return [(start_date.replace(day=1) + timedelta(days=31*i)).strftime("%b/%y").upper() for i in range(months)]

# --- INTERFACE ---
st.set_page_config(page_title="PMO Elite Impact", layout="wide")
local_css()

st.markdown(f"""
<div class="header-box">
    <h2 style="margin:0; color:#003366;">📑 Relatório PMO PROGRAMAS - Análise de Impacto Financeiro</h2>
</div>
""", unsafe_allow_html=True)

# 1. INFORMAÇÕES DO PROGRAMA
st.markdown('<div class="section-header">1. Informações do Programa</div>', unsafe_allow_html=True)
with st.container(border=True):
    c1, c2 = st.columns(2)
    prog_nome = c1.text_input("Nome do Programa", value=" ")
    prog_gerente = c2.text_input("Gerente do Programa", value=" ")
    justificativa = st.text_area("Justificativa da mudança / contexto", " ")

# 2. CENÁRIOS DE MUDANÇA (Ride and Show / Hide and Show)
st.markdown('<div class="section-header">2. Cenário de Mudança</div>', unsafe_allow_html=True)
abas_cenario = st.tabs(["Replanejamento (Rollout)", "Escopo (Retrabalho)", "Bugs (Instabilidade)", "Infraestrutura (Ociosidade)"])

with abas_cenario[0]: 
    show_rollout = st.checkbox("Informar Replanejamento (Rollout)")
    if show_rollout:
        c_r1, c_r2, c_r3 = st.columns(3)
        v_otm = c_r1.number_input("Otimista (Rollouts/mês)", value=6.0)
        v_pro = c_r2.number_input("Provável (Rollouts/mês)", value=5.0)
        v_pes = c_r3.number_input("Pessimista (Rollouts/mês)", value=3.0)
        vel_pert = (v_otm + 4*v_pro + v_pes) / 6
        st.info(f"Velocidade PERT Calculada: {vel_pert:.2f} rollouts/mês")

with abas_cenario[1]:
    show_escopo = st.checkbox("Informar Escopo (Retrabalho)")
    if show_escopo:
        st.number_input("Esforço de Retrabalho (Horas Totais)", value=0)
        st.multiselect("Itens Impactados", ["Frontend", "API", "Banco de Dados", "Processos"])

with abas_cenario[2]:
    show_bugs = st.checkbox("Informar Bugs (Instabilidade)")
    if show_bugs:
        st.selectbox("Nível de Gravidade", ["Baixa", "Média", "Crítica"])
        st.number_input("Qtd. de Bugs Identificados", value=0)

with abas_cenario[3]:
    show_infra = st.checkbox("Informar Infraestrutura (Ociosidade)")
    if show_infra:
        st.number_input("Horas de Ociosidade Estimadas", value=0)
        st.text_input("Recurso Ocioso")

# 3. MATRIZ DE ALOCAÇÃO
st.markdown('<div class="section-header">3. Matriz de Alocação e Orçamento</div>', unsafe_allow_html=True)
with st.container(border=True):
    m1, m2 = st.columns(2)
    data_inicio = m1.date_input("Início do Evento/Impacto", value=datetime.now(),format="DD/MM/YYYY")
    horizonte = m2.number_input("Meses (Horizonte)", min_value=1, value=4)
    lista_meses = get_meses_list(data_inicio, horizonte)

    with st.expander("➕ Adicionar Recurso ao Orçamento", expanded=True):
        f1, f2, f3 = st.columns(3)
        cargo = f1.selectbox("Cargo", ["Analista", "Consultor", "Especialista", "Gerente", "Desenvolvedor"])
        nivel = f2.selectbox("Nível", ["Junior", "Pleno", "Senior"])
        reg_cc = f3.text_input("Regional / Centro de Custo", " ")
        f4, f5, f6 = st.columns(3)
        taxa_h = f4.number_input("Taxa/Hora(R$)", value=150.0)
        hrs_base = f5.number_input("Horas/Mês (Base)", value=160)
        if f6.button("ADICIONAR RECURSO"):
            h_dist = {m: hrs_base for m in lista_meses}
            total_r = sum(h_dist.values()) * taxa_h
            db_conn.execute("INSERT INTO matriz_alocacao (projeto, cargo, nivel, reg, taxa, horas_json, total) VALUES (?,?,?,?,?,?,?)",
                         (prog_nome, cargo, nivel, reg_cc, taxa_h, json.dumps(h_dist), total_r))
            db_conn.commit()
            st.rerun()

    df_matriz = pd.read_sql_query(f"SELECT * FROM matriz_alocacao WHERE projeto='{prog_nome}'", db_conn)
    custo_base_total = df_matriz['total'].sum() if not df_matriz.empty else 0.0
    if not df_matriz.empty:
        st.dataframe(df_matriz[['cargo', 'nivel', 'reg', 'taxa', 'total']], use_container_width=True)
        st.metric("Burn Rate Médio / Orçamento Total da Equipe", format_brl(custo_base_total))

# 4. RESERVA E PERT
st.markdown('<div class="section-header">4. Análise de Riscos e Orçamento Total</div>', unsafe_allow_html=True)
delta_pert_risco = 0.15 
reserva_risco = custo_base_total * delta_pert_risco
total_cenario = custo_base_total + reserva_risco

r1, r2, r3 = st.columns(3)
r1.metric("Custo Estimado (Baseline)", format_brl(custo_base_total))
r2.metric("Reserva de Risco (Delta PERT)", format_brl(reserva_risco))
r3.metric("Orçamento Total Cenário (Base + Risco 95%)", format_brl(total_cenario))

# 5. IMPACTO MENSAL
st.markdown('<div class="section-header">5. Impacto Mensal na Margem do Programa</div>', unsafe_allow_html=True)
if horizonte > 0:
    df_mensal = pd.DataFrame({
        'Mês': lista_meses,
        'Custo evento (Base + Risco)': [total_cenario/horizonte]*horizonte
    })
    df_mensal['Impacto acumulado'] = df_mensal['Custo evento (Base + Risco)'].cumsum()
    st.table(df_mensal.style.format({'Custo evento (Base + Risco)': format_brl, 'Impacto acumulado': format_brl}))

# 6. TRÍPLICE RESTRIÇÃO
st.markdown('<div class="section-header">6. Análise integrada: tríplice de restrição</div>', unsafe_allow_html=True)
col_g1, col_g2 = st.columns([0.4, 0.6])
with col_g1:
    categories = ['Custo', 'Escopo', 'Tempo']
    fig_tri = go.Figure()
    fig_tri.add_trace(go.Scatterpolar(r=[80, 80, 80, 80], theta=categories+['Custo'], fill='toself', name='Planejado'))
    fig_tri.add_trace(go.Scatterpolar(r=[100, 110, 120, 100], theta=categories+['Custo'], fill='toself', name='Impacto'))
    fig_tri.update_layout(polar=dict(radialaxis=dict(visible=False)), showlegend=True, title="Triângulo de Restrição")
    st.plotly_chart(fig_tri, use_container_width=True)

# 7. DRE E MARGEM FINAL
st.markdown('<div class="section-header">7. DRE do Programa: Análise de margem final</div>', unsafe_allow_html=True)
with st.container(border=True):
    d1, d2, d3 = st.columns(3)
    margem_meta = d1.number_input("Margem inicial (Meta) %", value=35.0)
    receita_liq = d2.number_input("Receita líquida atual", min_value=1.0 , value=5000.0, step=1000.0)
    custo_eac_atual = d3.number_input("Custo total atual (EAC)", min_value=1.0, value=1000.0, step=1000.0)

    margem_atual = (1 - (custo_eac_atual/receita_liq)) * 100
    novo_eac = custo_eac_atual + total_cenario
    margem_final = (1 - (novo_eac/receita_liq)) * 100
    erosao = margem_atual - margem_final

    st.divider()
    res1, res2, res3 = st.columns(3)
    res1.metric("Margem atual", f"{margem_atual:.2f}%")
    res2.metric("Margem projetada total", f"{margem_final:.2f}%", delta=f"-{erosao:.2f}%", delta_color="inverse")
    res3.metric("Erosão de Margem", f"{erosao:.2f} p.p.")

# 8. GRÁFICO DE EROSÃO
st.markdown('<div class="section-header">8. Gráfico da Erosão de Margem</div>', unsafe_allow_html=True)
df_erosao = pd.DataFrame({'Cenário': ['Meta', 'Atual', 'Projetado'], 'Margem %': [margem_meta, margem_atual, margem_final]})
fig_bar = px.bar(df_erosao, x='Cenário', y='Margem %', text_auto='.2f', color='Cenário', color_discrete_sequence=['#455a64', '#00bfa5', '#d32f2f'])
st.plotly_chart(fig_bar, use_container_width=True)

# 9. GERAÇÃO DE PDF
if st.sidebar.button("📊 GERAR ARQUIVO EM PDF"):
    pdf = RelatorioElite()
    pdf.add_page()
    pdf.add_watermark()
    
    pdf.set_fill_color(0, 51, 102); pdf.set_font('Arial', 'B', 11); pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, " 1. INFORMACOES DO PROGRAMA", 0, 1, 'L', fill=True)
    pdf.set_text_color(0, 0, 0); pdf.set_font('Arial', '', 10); pdf.ln(2)
    pdf.cell(0, 8, f"Programa: {prog_nome.upper()}", 0, 1)
    pdf.cell(0, 8, f"Gerente: {prog_gerente}", 0, 1)
    pdf.multi_cell(0, 6, f"Contexto: {justificativa}")
    pdf.ln(5)
    
    pdf.set_fill_color(0, 51, 102); pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, " 2. ANALISE FINANCEIRA E EROSAO", 0, 1, 'L', fill=True)
    pdf.set_text_color(0, 0, 0); pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f"Custo Evento (Base + Risco): {format_brl(total_cenario)}", 0, 1)
    pdf.cell(0, 8, f"Margem Atual: {margem_atual:.2f}% | Margem Projetada: {margem_final:.2f}%", 0, 1)
    pdf.set_font('Arial', 'B', 10); pdf.set_text_color(180, 0, 0)
    pdf.cell(0, 8, f"EROSAO DE MARGEM: {erosao:.2f} p.p.", 0, 1)
    
    try:
        img_tri = fig_tri.to_image(format="png", width=500, height=400)
        img_bar = fig_bar.to_image(format="png", width=500, height=400)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as t1, tempfile.NamedTemporaryFile(delete=False, suffix=".png") as t2:
            t1.write(img_tri); t2.write(img_bar)
            pdf.image(t1.name, x=10, y=pdf.get_y()+5, w=90)
            pdf.image(t2.name, x=105, y=pdf.get_y()+5, w=90)
    except:
        pdf.cell(0, 10, "[Imagens indisponiveis no ambiente atual]", 0, 1)

    output = pdf.output(dest='S')
    st.sidebar.download_button("📥 Baixar Dossiê PDF", data=bytes(output), file_name="Dossie_Impacto.pdf")
