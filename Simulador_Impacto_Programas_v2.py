import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import plotly.graph_objects as go
from fpdf import FPDF
from datetime import datetime
import io

# --- CONFIGURAÇÕES DE ESCALA ---
STEP_MONEY = 10.0
STEP_MACRO_MONEY = 1000.0
STEP_RESOURCE = 1

st.set_page_config(page_title="MV PMO Intelligence PRO", layout="wide")

# --- DATABASE INTEGRADA (RECURSOS + CENÁRIOS) ---
def init_db():
    conn = sqlite3.connect('pmo_decision_hub.db', check_same_thread=False)
    c = conn.cursor()
    # Tabela de Recursos Temporários (Sessão Atual)
    c.execute('''CREATE TABLE IF NOT EXISTS recursos_temp 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, funcao TEXT, senioridade TEXT, custo_h REAL, horas INTEGER, subtotal REAL)''')
    # Tabela de Histórico de Cenários Salvos
    c.execute('''CREATE TABLE IF NOT EXISTS cenarios_salvos 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, projeto TEXT, nome_cenario TEXT, impacto_p95 REAL, margem_resultante REAL, data_gravacao TEXT)''')
    conn.commit()
    return conn

db_conn = init_db()

# --- FUNÇÕES DE CÁLCULO ---
def format_currency(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def calc_pert(o, m, p):
    return (o + 4*m + p) / 6

def run_monte_carlo(o, m, p, n=5000):
    if o >= p: return m, m
    sims = np.random.triangular(o, m, p, n)
    return np.mean(sims), np.percentile(sims, 95)

# --- INTERFACE SIDEBAR ---
with st.sidebar:
    st.title("🛡️ MV PMO Master")
    projeto = st.selectbox("Selecione o Programa", ["UNIMED SERRA GAUCHA", "INS", "CLINICA GIRASSOL", "EINSTEIN", "RHP"])
    receita_net = st.number_input("Receita Líquida (R$)", value=4500000.0, step=STEP_MACRO_MONEY)
    custo_eac_atual = st.number_input("Custo EAC Atual (R$)", value=4000000.0, step=STEP_MACRO_MONEY)
    st.divider()
    st.info("Dica: Use o Hub de Cenários para comparar estratégias de mitigação.")

# --- CORPO PRINCIPAL ---
t1, t2 = st.tabs(["🚀 Simulação Ativa", "📚 Hub de Cenários & Comparativos"])

with t1:
    st.header(f"Simulação de Impacto: {projeto}")
    
    col_input, col_viz = st.columns([1, 1])
    
    with col_input:
        st.subheader("1. Variáveis de Mudança")
        cat = st.selectbox("Categoria", ["Replanejamento", "Escopo Adicional", "Crise Técnica"])
        
        with st.expander("👥 Alocação de Staff Adicional", expanded=True):
            with st.form("add_res"):
                f1, f2, f3 = st.columns([2,1,1])
                func = f1.selectbox("Papel", ["Consultor", "Dev", "PMO", "Arquiteto"])
                ch = f2.number_input("Custo/H", value=150.0, step=STEP_MONEY)
                hr = f3.number_input("Horas", value=160, step=STEP_RESOURCE)
                if st.form_submit_button("Incluir no Cenário"):
                    db_conn.execute("INSERT INTO recursos_temp (funcao, senioridade, custo_h, horas, subtotal) VALUES (?,?,?,?,?)",
                                 (func, "Sr", ch, hr, ch*hr))
                    db_conn.commit()
                    st.rerun()

        df_res = pd.read_sql_query("SELECT * FROM recursos_temp", db_conn)
        custo_staff = df_res['subtotal'].sum() if not df_res.empty else 0.0
        st.dataframe(df_res[['funcao', 'horas', 'subtotal']], use_container_width=True)
        if st.button("🗑️ Limpar Recursos"):
            db_conn.execute("DELETE FROM recursos_temp")
            db_conn.commit()
            st.rerun()

    with col_viz:
        st.subheader("2. Análise de Risco (Monte Carlo)")
        o = st.number_input("Custo Mínimo (Otimista)", value=(custo_staff * 0.8) if custo_staff > 0 else 10000.0, step=STEP_MONEY)
        p = st.number_input("Custo Máximo (Pessimista)", value=(custo_staff * 1.5) if custo_staff > 0 else 50000.0, step=STEP_MONEY)
        
        _, p95 = run_monte_carlo(o, custo_staff if custo_staff > 0 else (o+p)/2, p)
        
        # Margens
        margem_at = ((receita_net - custo_eac_atual) / receita_net) * 100
        margem_new = ((receita_net - (custo_eac_atual + p95)) / receita_net) * 100
        
        st.metric("Impacto no EAC (Teto P95)", format_currency(p95), delta=f"{p95/(receita_net)*100:.2f}% da Receita", delta_color="inverse")
        
        fig_m = go.Figure(go.Indicator(
            mode = "gauge+number+delta",
            value = margem_new,
            title = {'text': "Margem Final Projetada (%)"},
            delta = {'reference': margem_at, 'relative': False},
            gauge = {'axis': {'range': [None, 50]},
                     'bar': {'color': "#C0392B"},
                     'steps' : [
                         {'range': [0, 15], 'color': "red"},
                         {'range': [15, 25], 'color': "yellow"},
                         {'range': [25, 50], 'color': "green"}]}))
        st.plotly_chart(fig_m, use_container_width=True)

    st.divider()
    st.subheader("3. Protocolar este Cenário")
    nome_cenario = st.text_input("Dê um nome a esta simulação (ex: 'Mitigação com Consultoria Externa')")
    if st.button("💾 Salvar Snapshot para Comparação"):
        db_conn.execute("INSERT INTO cenarios_salvos (projeto, nome_cenario, impacto_p95, margem_resultante, data_gravacao) VALUES (?,?,?,?,?)",
                     (projeto, nome_cenario, p95, margem_new, datetime.now().strftime("%d/%m %H:%M")))
        db_conn.commit()
        st.success("Cenário salvo no Hub!")

with t2:
    st.header("📚 Inteligência Comparativa")
    df_h = pd.read_sql_query(f"SELECT * FROM cenarios_salvos WHERE projeto = '{projeto}'", db_conn)
    
    if not df_h.empty:
        col_list, col_chart = st.columns([1, 1])
        
        with col_list:
            st.write("**Cenários Protocolados**")
            st.table(df_h[['nome_cenario', 'impacto_p95', 'margem_resultante', 'data_gravacao']])
            if st.button("🗑️ Excluir Histórico"):
                db_conn.execute(f"DELETE FROM cenarios_salvos WHERE projeto = '{projeto}'")
                db_conn.commit()
                st.rerun()
        
        with col_chart:
            st.write("**Gráfico de Decisão: Impacto vs Margem**")
            fig_comp = go.Figure()
            fig_comp.add_trace(go.Bar(x=df_h['nome_cenario'], y=df_h['margem_resultante'], marker_color='#003366', name="Margem (%)"))
            fig_comp.update_layout(yaxis_title="Margem Final (%)", xaxis_title="Cenário")
            st.plotly_chart(fig_comp, use_container_width=True)
    else:
        st.warning("Nenhum cenário salvo para este projeto.")
