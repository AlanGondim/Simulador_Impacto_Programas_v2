import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from fpdf import FPDF
from datetime import datetime

# --- CONFIGURAÇÕES DE ESCALA ---
STEP_MONEY = 10.0
STEP_MACRO_MONEY = 1000.0
STEP_RESOURCE = 1

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect('pmo_master_v3.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recursos (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 projeto TEXT, funcao TEXT, senioridade TEXT, custo_h REAL, horas INTEGER, subtotal REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cenarios (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 projeto TEXT, nome_cenario TEXT, impacto_p95 REAL, margem REAL, data TEXT)''')
    conn.commit()
    return conn

db_conn = init_db()

# --- FUNÇÕES CORE ---
def format_currency(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def run_monte_carlo(o, m, p, n=5000):
    if o >= p: return float(m), float(m)
    sims = np.random.triangular(o, m, p, n)
    return float(np.mean(sims)), float(np.percentile(sims, 95))

class ExecutivePDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'PARECER TECNICO DE IMPACTO ECONOMICO - PMO MV', 0, 1, 'R')
        self.ln(10)

# --- INTERFACE ---
st.title("🛡️ MV PMO Decision Intelligence PRO")

with st.sidebar:
    st.title("⚙️ Configuração Master")
    proj = st.selectbox("Programa", ["UNIMED SERRA GAUCHA", "INS", "CLINICA GIRASSOL", "EINSTEIN", "RHP"])
    receita_net = st.number_input("Receita Líquida (R$)", value=4719147.0, step=STEP_MACRO_MONEY)
    custo_eac_base = st.number_input("Custo Atual EAC (R$)", value=4963246.0, step=STEP_MACRO_MONEY)

tab1, tab2, tab3 = st.tabs(["🚀 Simulação Ativa", "📊 Sensibilidade", "📚 Hub de Cenários"])

with tab1:
    st.subheader("1. Categorias de Impacto (Parametrização Técnica)")
    
    # HIDE AND SHOW POR CATEGORIA
    cat_impacto = st.selectbox("Selecione a Categoria da Mudança:", 
                              ["Replanejamento (Rollout)", "Retrabalho (Escopo)", "Instabilidade (Bugs)", "Infraestrutura (Ociosidade)"])
    
    impacto_calculado_cat = 0.0

    with st.expander(f"Configurar Detalhes: {cat_impacto}", expanded=True):
        col_cat1, col_cat2, col_cat3 = st.columns(3)
        
        if cat_impacto == "Replanejamento (Rollout)":
            qtd_unidades = col_cat1.number_input("Unidades Restantes", value=10, step=STEP_RESOURCE)
            burn_mensal = col_cat2.number_input("Burn Rate Equipe (Mês)", value=150000.0, step=STEP_MACRO_MONEY)
            pace_novo = col_cat3.slider("Novo Pace (Unidades/Mês)", 0.5, 5.0, 2.0)
            impacto_calculado_cat = (qtd_unidades / pace_novo) * burn_mensal

        elif cat_impacto == "Retrabalho (Escopo)":
            horas_retrabalho = col_cat1.number_input("Total Horas Estimadas", value=200, step=STEP_RESOURCE)
            custo_hora_medio = col_cat2.number_input("Custo Médio H/H", value=180.0, step=STEP_MONEY)
            impacto_calculado_cat = horas_retrabalho * custo_hora_medio

        elif cat_impacto == "Instabilidade (Bugs)":
            qtd_bugs = col_cat1.number_input("Qtd de Chamados Críticos", value=50, step=STEP_RESOURCE)
            horas_por_bug = col_cat2.number_input("Média Horas/Bug", value=8, step=STEP_RESOURCE)
            custo_h_bug = col_cat3.number_input("Custo H/H Dev", value=140.0, step=STEP_MONEY)
            impacto_calculado_cat = qtd_bugs * horas_por_bug * custo_h_bug

        elif cat_impacto == "Infraestrutura (Ociosidade)":
            dias_parados = col_cat1.number_input("Dias de Equipe Parada", value=5, step=STEP_RESOURCE)
            custo_dia_equipe = col_cat2.number_input("Custo Diário Operacional", value=12000.0, step=STEP_MACRO_MONEY)
            impacto_calculado_cat = dias_parados * custo_dia_equipe

    st.info(f"Impacto Estimado na Categoria: {format_currency(impacto_calculado_cat)}")

    st.subheader("2. Alocação Adicional de Recursos")
    with st.expander("➕ Adicionar Staff extra para mitigação", expanded=False):
        with st.form("form_rec"):
            f1, f2, f3 = st.columns([2,1,1])
            func = f1.selectbox("Papel", ["Consultor", "Analista", "Arquiteto", "Dev", "PMO"])
            ch = f2.number_input("Custo/Hora", value=130.0, step=STEP_MONEY)
            hr = f3.number_input("Qtd Horas", value=160, step=STEP_RESOURCE)
            if st.form_submit_button("Adicionar Recurso"):
                db_conn.execute("INSERT INTO recursos (projeto, funcao, senioridade, custo_h, horas, subtotal) VALUES (?,?,'Sr',?,?,?)",
                             (proj, func, ch, hr, ch*hr))
                db_conn.commit()
                st.rerun()
    
    df_rec = pd.read_sql_query(f"SELECT * FROM recursos WHERE projeto = '{proj}'", db_conn)
    custo_recursos = df_rec['subtotal'].sum() if not df_rec.empty else 0.0

    # 3. RESULTADOS E TRIÂNGULO DE FERRO
    st.divider()
    m_nominal = impacto_calculado_cat + custo_recursos
    
    # Monte Carlo Sidebar/Inputs para o Triângulo
    o = st.sidebar.number_input("Cenário Otimista (Total)", value=m_nominal * 0.85, step=STEP_MACRO_MONEY)
    p = st.sidebar.number_input("Cenário Pessimista (Total)", value=m_nominal * 1.6, step=STEP_MACRO_MONEY)
    
    val_pert, val_p95 = run_monte_carlo(o, m_nominal, p)
    margem_final = (1 - ((custo_eac_base + val_p95) / receita_net)) * 100 if receita_net > 0 else 0

    col_res1, col_res2 = st.columns([1, 1])
    with col_res1:
        st.metric("Custo P95 (Teto de Risco)", format_currency(val_p95))
        st.metric("Margem Final Projetada", f"{margem_final:.2f}%", delta=f"{margem_final - ((1-(custo_eac_base/receita_net))*100):.2f}%", delta_color="inverse")
        
        if st.button("📑 Gerar Relatório PDF"):
            pdf = ExecutivePDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, f"Projeto: {proj} | Categoria: {cat_impacto}", ln=1)
            pdf.cell(0, 10, f"Impacto Total P95: {format_currency(val_p95)}", ln=1)
            pdf.cell(0, 10, f"Margem Resultante: {margem_final:.2f}%", ln=1)
            pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace')
            st.download_button("📥 Baixar Relatório Executivo", data=pdf_bytes, file_name=f"Parecer_{proj}.pdf", mime="application/pdf")

    with col_res2:
        # Triângulo de Ferro dinâmico
        cost_score = val_p95 / (m_nominal * 1.2) if m_nominal > 0 else 1.0
        time_score = 1.5 if cat_impacto == "Replanejamento (Rollout)" else 1.1
        scope_score = 1.4 if cat_impacto == "Retrabalho (Escopo)" else 1.1
        
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=[1,1,1,1], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Baseline'))
        fig_radar.add_trace(go.Scatterpolar(r=[cost_score, time_score, scope_score, cost_score], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Cenário Atual', line_color='red'))
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 2])), height=350, title="Equilíbrio do Projeto")
        st.plotly_chart(fig_radar, use_container_width=True)

with tab2:
    st.header("🔍 Análise de Sensibilidade do Custo")
    # Criação de DataFrame consolidado para o gráfico
    dados_sensibilidade = []
    if impacto_calculado_cat > 0:
        dados_sensibilidade.append({'Origem': 'Categoria de Impacto', 'Valor': impacto_calculado_cat})
    if not df_rec.empty:
        for _, r in df_rec.iterrows():
            dados_sensibilidade.append({'Origem': f"Recurso: {r['funcao']}", 'Valor': r['subtotal']})
    
    if dados_sensibilidade:
        df_sens = pd.DataFrame(dados_sensibilidade)
        fig_sens = px.bar(df_sens, x='Origem', y='Valor', color='Origem', title="Composição do Impacto Financeiro")
        st.plotly_chart(fig_sens, use_container_width=True)
    else:
        st.info("Aguardando preenchimento de dados para análise.")

with tab3:
    st.header("📚 Histórico de Cenários")
    nome_cenario = st.text_input("Nome desta Simulação:", placeholder="Ex: Mitigação Plano B")
    if st.button("💾 Salvar Snapshot"):
        db_conn.execute("INSERT INTO cenarios (projeto, nome_cenario, impacto_p95, margem, data) VALUES (?,?,?,?,?)",
                     (proj, nome_cenario, val_p95, margem_final, datetime.now().strftime("%d/%m %H:%M")))
        db_conn.commit()
        st.success("Snapshot gravado com sucesso.")
    
    df_h = pd.read_sql_query(f"SELECT * FROM cenarios WHERE projeto = '{proj}'", db_conn)
    st.dataframe(df_h[['nome_cenario', 'impacto_p95', 'margem', 'data']], use_container_width=True)
