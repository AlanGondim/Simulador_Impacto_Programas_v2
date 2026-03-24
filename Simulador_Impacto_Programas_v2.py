import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from fpdf import FPDF
from datetime import datetime
import io

# --- CONFIGURAÇÕES DE ESCALA ---
STEP_MONEY = 10.0
STEP_MACRO_MONEY = 1000.0
STEP_RESOURCE = 1

# --- DATABASE ENGINE (PERSISTÊNCIA DE DADOS) ---
def init_db():
    conn = sqlite3.connect('pmo_master_enterprise.db', check_same_thread=False)
    c = conn.cursor()
    # Tabela de Recursos por Projeto
    c.execute('''CREATE TABLE IF NOT EXISTS recursos (
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 projeto TEXT, funcao TEXT, custo_h REAL, horas INTEGER, subtotal REAL)''')
    # Tabela de Histórico de Cenários (Snapshots)
    c.execute('''CREATE TABLE IF NOT EXISTS cenarios (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
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

# Classe PDF com tratamento de erro de versão (Agnóstica)
class ExecutivePDF(FPDF):
    def header(self):
        try:
            self.image("Logomarca MV Atualizada.png", 10, 8, 30)
        except:
            pass
        self.set_font('Arial', 'B', 15)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'PARECER TECNICO DE IMPACTO ECONOMICO - PMO MV', 0, 1, 'R')
        self.ln(10)

# --- INTERFACE E GOVERNANÇA ---
st.set_page_config(page_title="MV PMO Intelligence PRO", layout="wide")

with st.sidebar:
    try:
        st.image("Logomarca MV Atualizada.png", width=150)
    except:
        st.title("MV PMO")
    
    st.header("⚙️ Parâmetros do Programa")
    proj = st.selectbox("Selecione o Projeto/Programa", ["UNIMED SERRA GAUCHA", "INS", "CLINICA GIRASSOL", "EINSTEIN", "RHP"])
    receita_net = st.number_input("Receita Líquida (R$)", value=4719147.0, step=STEP_MACRO_MONEY)
    custo_eac_base = st.number_input("Custo Atual EAC (R$)", value=4963246.0, step=STEP_MACRO_MONEY)
    st.divider()
    st.info("Este simulador utiliza Modelagem de Monte Carlo para calcular a exposição de risco P95.")

# --- TABS PRINCIPAIS ---
tab1, tab2, tab3 = st.tabs(["🚀 Simulação Ativa", "📊 Sensibilidade & Pareto", "📚 Hub de Cenários"])

with tab1:
    # 1. CATEGORIAS DE IMPACTO (PARAMETRIZAÇÃO TÉCNICA)
    st.subheader("1. Categorias de Impacto (Causa Raiz)")
    cat_impacto = st.selectbox("Tipo de Incidente/Mudança:", 
                              ["Replanejamento (Rollout)", "Retrabalho (Escopo)", "Instabilidade (Bugs)", "Infraestrutura (Ociosidade)"])
    
    impacto_calculado_cat = 0.0

    with st.container(border=True):
        col_cat1, col_cat2, col_cat3 = st.columns(3)
        if cat_impacto == "Replanejamento (Rollout)":
            qtd_unidades = col_cat1.number_input("Unidades Restantes", value=10, step=STEP_RESOURCE)
            burn_mensal = col_cat2.number_input("Burn Rate Mensal Equipe", value=150000.0, step=STEP_MACRO_MONEY)
            pace_novo = col_cat3.slider("Novo Pace (Un/Mês)", 0.5, 5.0, 2.0)
            impacto_calculado_cat = (qtd_unidades / pace_novo) * burn_mensal

        elif cat_impacto == "Retrabalho (Escopo)":
            horas_retrabalho = col_cat1.number_input("H/H Total Estimada", value=200, step=STEP_RESOURCE)
            custo_hora_medio = col_cat2.number_input("Custo Médio H/H", value=180.0, step=STEP_MONEY)
            impacto_calculado_cat = horas_retrabalho * custo_hora_medio

        elif cat_impacto == "Instabilidade (Bugs)":
            qtd_bugs = col_cat1.number_input("Qtd de Chamados Críticos", value=50, step=STEP_RESOURCE)
            horas_por_bug = col_cat2.number_input("Média Horas/Bug", value=8, step=STEP_RESOURCE)
            impacto_calculado_cat = qtd_bugs * horas_por_bug * 145.0

        elif cat_impacto == "Infraestrutura (Ociosidade)":
            dias_parados = col_cat1.number_input("Dias de Bloqueio", value=5, step=STEP_RESOURCE)
            custo_dia_equipe = col_cat2.number_input("Custo Diário Operacional", value=12000.0, step=STEP_MACRO_MONEY)
            impacto_calculado_cat = dias_parados * custo_dia_equipe

    st.info(f"💡 Impacto Base Estimado: {format_currency(impacto_calculado_cat)}")

    # 2. GESTÃO DE RECURSOS (CRUD DINÂMICO)
    st.subheader("2. Alocação de Recursos Adicionais (Staffing)")
    
    with st.expander("➕ Adicionar Novo Recurso para Mitigação", expanded=False):
        with st.form("form_rec_add", clear_on_submit=True):
            f1, f2, f3 = st.columns([2,1,1])
            func = f1.selectbox("Papel/Função", ["Consultor Sr", "Analista Pl", "Arquiteto", "Desenvolvedor", "Coordenador PMO"])
            ch = f2.number_input("Custo/Hora (R$)", value=140.0, step=STEP_MONEY)
            hr = f3.number_input("Qtd de Horas", value=160, step=STEP_RESOURCE)
            if st.form_submit_button("Vincular ao Projeto"):
                db_conn.execute("INSERT INTO recursos (projeto, funcao, custo_h, horas, subtotal) VALUES (?,?,?,?,?)",
                             (proj, func, ch, hr, ch*hr))
                db_conn.commit()
                st.rerun()

    # Visualização e Exclusão Individual
    df_rec = pd.read_sql_query(f"SELECT * FROM recursos WHERE projeto = '{proj}'", db_conn)
    custo_staff_total = 0.0
    
    if not df_rec.empty:
        custo_staff_total = df_rec['subtotal'].sum()
        for idx, row in df_rec.iterrows():
            with st.container(border=True):
                c_1, c_2, c_3, c_4 = st.columns([2, 1, 1, 0.5])
                c_1.write(f"👤 **{row['funcao']}**")
                c_2.write(f"{row['horas']}h x {format_currency(row['custo_h'])}")
                c_3.write(f"**{format_currency(row['subtotal'])}**")
                if c_4.button("🗑️", key=f"del_{row['id']}"):
                    db_conn.execute(f"DELETE FROM recursos WHERE id = {row['id']}")
                    db_conn.commit()
                    st.rerun()
    else:
        st.write("Nenhum recurso adicional alocado.")

    # 3. RESULTADOS FINANCEIROS E RISCO (MONTE CARLO)
    st.divider()
    m_nominal = impacto_calculado_cat + custo_staff_total
    
    # Inputs de Risco (Sidebar)
    o = st.sidebar.number_input("Cenário Otimista (Total)", value=m_nominal * 0.9, step=STEP_MACRO_MONEY)
    p = st.sidebar.number_input("Cenário Pessimista (Total)", value=m_nominal * 1.5, step=STEP_MACRO_MONEY)
    
    val_pert, val_p95 = run_monte_carlo(o, m_nominal, p)
    margem_original = (1 - (custo_eac_base / receita_net)) * 100 if receita_net > 0 else 0
    margem_final = (1 - ((custo_eac_base + val_p95) / receita_net)) * 100 if receita_net > 0 else 0

    col_res1, col_res2 = st.columns([1, 1])
    with col_res1:
        st.metric("Impacto Financeiro P95 (Teto)", format_currency(val_p95), delta="Exposição de Risco")
        st.metric("Margem Final Projetada", f"{margem_final:.2f}%", 
                  delta=f"{margem_final - margem_original:.2f}% de erosão", delta_color="inverse")
        
        # GERAÇÃO DE PDF PROFISSIONAL (FIXED)
        if st.button("📑 Gerar Relatório de Governança (PDF)"):
            pdf = ExecutivePDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, f"Programa: {proj}", ln=1)
            pdf.cell(0, 10, f"Categoria de Impacto: {cat_impacto}", ln=1)
            pdf.cell(0, 10, f"Impacto P95: {format_currency(val_p95)}", ln=1)
            pdf.cell(0, 10, f"Margem Resultante: {margem_final:.2f}%", ln=1)
            
            try:
                pdf_output = pdf.output()
                if isinstance(pdf_output, str): # fpdf clássico
                    pdf_bytes = pdf_output.encode('latin-1')
                else: # fpdf2 (bytes)
                    pdf_bytes = pdf_output
            except:
                pdf_bytes = pdf.output(dest='S').encode('latin-1')
                
            st.download_button("📥 Baixar Parecer Executivo", data=pdf_bytes, file_name=f"Parecer_Tecnico_{proj}.pdf", mime="application/pdf")

    with col_res2:
        # Triângulo de Ferro Dinâmico
        cost_v = val_p95 / (m_nominal * 1.2) if m_nominal > 0 else 1.0
        time_v = 1.4 if "Replanejamento" in cat_impacto else 1.1
        scope_v = 1.3 if "Retrabalho" in cat_impacto else 1.1
        
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=[1,1,1,1], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Baseline'))
        fig_radar.add_trace(go.Scatterpolar(r=[cost_v, time_v, scope_v, cost_v], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Cenário Atual', line_color='red'))
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 2])), height=350, title="Impacto no Triângulo de Ferro")
        st.plotly_chart(fig_radar, use_container_width=True)

with tab2:
    st.header("🔍 Análise de Sensibilidade")
    # Composição do Custo
    dados_sens = []
    if impacto_calculado_cat > 0: dados_sens.append({'Origem': f'Causa: {cat_impacto}', 'Valor': impacto_calculado_cat})
    if not df_rec.empty:
        for _, r in df_rec.iterrows():
            dados_sens.append({'Origem': f"Staff: {r['funcao']}", 'Valor': r['subtotal']})
    
    if dados_sens:
        df_sens = pd.DataFrame(dados_sens)
        fig_pie = px.pie(df_sens, values='Valor', names='Origem', hole=0.4, title="Quem está consumindo a Margem?")
        st.plotly_chart(fig_pie, use_container_width=True)
        
        fig_pareto = px.bar(df_sens.sort_values(by='Valor', ascending=False), x='Origem', y='Valor', title="Ranking de Impacto Financeiro")
        st.plotly_chart(fig_pareto, use_container_width=True)
    else:
        st.info("Nenhum dado disponível para análise de sensibilidade.")

with tab3:
    st.header("📚 Hub de Cenários & Snapshots")
    nome_cen = st.text_input("Nome do Snapshot (ex: Mitigação Plano B):", placeholder="Digite um nome para salvar...")
    
    if st.button("💾 Salvar este Cenário"):
        if nome_cen:
            db_conn.execute("INSERT INTO cenarios (projeto, nome_cenario, impacto_p95, margem, data) VALUES (?,?,?,?,?)",
                         (proj, nome_cen, val_p95, margem_final, datetime.now().strftime("%d/%m %H:%M")))
            db_conn.commit()
            st.success(f"Cenário '{nome_cen}' protocolado com sucesso!")
        else:
            st.warning("Por favor, dê um nome ao cenário antes de salvar.")
    
    st.divider()
    st.subheader("Cenários Protocolados")
    df_h = pd.read_sql_query(f"SELECT * FROM cenarios WHERE projeto = '{proj}'", db_conn)
    if not df_h.empty:
        st.dataframe(df_h[['nome_cenario', 'impacto_p95', 'margem', 'data']], use_container_width=True)
        if st.button("🗑️ Limpar Histórico de Cenários"):
            db_conn.execute(f"DELETE FROM cenarios WHERE projeto = '{proj}'")
            db_conn.commit()
            st.rerun()
    else:
        st.info("Nenhum cenário salvo para este projeto.")
