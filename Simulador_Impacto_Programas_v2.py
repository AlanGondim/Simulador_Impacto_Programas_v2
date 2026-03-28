import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
import sqlite3
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from fpdf import FPDF
from datetime import datetime, timedelta
import tempfile
import json

# --- CONFIGURAÇÕES DE INTERFACE ---
def local_css():
    st.markdown("""
    <style>
        .main { background-color: #f8f9fa; }
        .stMetric { background-color: white; padding: 15px; border-radius: 8px; border-top: 4px solid #003366; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .header-box { background-color: white; padding: 20px; border-radius: 10px; border-left: 10px solid #003366; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .section-header { color: #003366; font-weight: bold; margin-top: 30px; border-bottom: 2px solid #e0e0e0; padding-bottom: 5px; font-size: 1.2rem; }
    </style>
    """, unsafe_allow_html=True)

# --- ENGINE DE DADOS ---
def init_db():
    conn = sqlite3.connect('pmo_elite_v2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS matriz_alocacao 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, projeto TEXT, cargo TEXT, nivel TEXT, 
                  reg TEXT, taxa REAL, horas_json TEXT, total REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS resumo_impacto 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data_geracao TEXT, projeto TEXT, 
                  custo_total REAL, margem_antes REAL, margem_depois REAL, erosao REAL)''')
    conn.commit()
    return conn

db_conn = init_db()

# --- CLASSE PDF PROFISSIONAL ---
class RelatorioExecutivo(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'DOSSIE DE IMPACTO FINANCEIRO E EROSAO DE MARGEM', 0, 1, 'C')
        self.set_font('Arial', 'I', 9)
        self.cell(0, 5, 'PMO CORPORATIVO - DIRETORIA DE OPERACOES', 0, 1, 'C')
        self.ln(5)
        self.set_draw_color(0, 51, 102)
        self.set_line_width(0.8)
        self.line(10, 28, 200, 28)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 10, f'Pagina {self.page_no()} | CONFIDENCIAL | Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 0, 'C')

    def assinaturas(self):
        self.set_y(-50)
        self.set_font('Arial', 'B', 8)
        self.set_draw_color(150, 150, 150)
        self.line(20, self.get_y(), 90, self.get_y())
        self.line(120, self.get_y(), 190, self.get_y())
        self.cell(95, 8, 'Diretoria de Operacoes', 0, 0, 'C')
        self.cell(95, 8, 'Gerencia do Programa', 0, 1, 'C')

    def chapter_title(self, label):
        self.set_font('Arial', 'B', 11)
        self.set_fill_color(230, 230, 230)
        self.set_text_color(0, 51, 102)
        self.cell(0, 8, f" {label}", 0, 1, 'L', fill=True)
        self.ln(3)

# --- FUNÇÕES DE SUPORTE ---
def format_brl(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def metric_card_custom(label, value, delta_val):
    is_negative = delta_val > 0 
    color = "#d32f2f" if is_negative else "#2e7d32"
    bg_color = "#ffeeee" if is_negative else "#e8f5e9"
    arrow = "↓" if is_negative else "↑"
    
    st.markdown(f"""
    <div style="background-color: white; padding: 15px; border-radius: 8px; border-top: 4px solid {color}; box-shadow: 0 2px 4px rgba(0,0,0,0.05); text-align: left;">
        <p style="color: #666; font-size: 14px; margin: 0;">{label}</p>
        <h2 style="margin: 5px 0; color: #333;">{value}</h2>
        <div style="background-color: {bg_color}; color: {color}; padding: 2px 8px; border-radius: 4px; display: inline-block; font-weight: bold; font-size: 14px;">
            {arrow} {delta_val:.2f}%
        </div>
    </div>
    """, unsafe_allow_html=True)

def get_meses_list(start_date, months):
    return [(start_date.replace(day=1) + timedelta(days=31*i)).strftime("%b/%y").upper() for i in range(months)]

# --- INTERFACE ---
st.set_page_config(page_title="Simulador de Impacto Financeiro", layout="wide")
local_css()

st.markdown('<div class="header-box"><h2 style="margin:0; color:#003366;">📑 Análise de Impacto Financeiro - PMO PROGRAMAS</h2></div>', unsafe_allow_html=True)

# --- LISTA DE PROGRAMAS ---
LISTA_PROGRAMAS = [
    " ", "INS", "EINSTEIN", "CEMA", "MOGI", "RHP", 
    "HCM", "HCS", "SoulBene Digital", "Girassol", "Bauru"
]

# Adicione esta lista com os nomes dos gerentes
LISTA_GERENTES = [" ", "Mariane Mylius", "Rosemary Lopes", "Lizia Cunha", "Sergio Carvalho", "Roberio Matos ", "Kamyla Ferrarezi", "Cristiano Gomes", "Ana Alencar", "Marcela Prates", "Luiza Liberal", "Jose Alexandre" ]

# 1. INFORMAÇÕES DO PROGRAMA
st.markdown('<div class="section-header">1. Informações do Programa</div>', unsafe_allow_html=True)
with st.container(border=True):
    c1, c2 = st.columns(2)
    prog_nome = c1.selectbox("Programa", options=LISTA_PROGRAMAS, key="sel_prog")
    prog_gerente = c2.selectbox("Gerente do Programa", options=LISTA_GERENTES, key="sel_gerente")
    contexto = st.text_area("Contexto da Mudança", placeholder="Descreva o motivo do impacto financeiro...")

# 2. CENÁRIOS DE MUDANÇA (Ride and Show / Hide and Show)
st.markdown('<div class="section-header">2. Cenário de Mudança</div>', unsafe_allow_html=True)
abas_cenario = st.tabs(["Replanejamento (Rollout)", "Escopo (Retrabalho)", "Bugs (Instabilidade)", "Infraestrutura (Ociosidade)"])

with abas_cenario[0]: 
    show_rollout = st.checkbox("Informar Replanejamento (Rollout)")
    if show_rollout:
        c_r1, c_r2, c_r3 = st.columns(3)
        v_otm = c_r1.number_input("Otimista (Rollouts/mês)", value=6.0, step=1.0)
        v_pro = c_r2.number_input("Provável (Rollouts/mês)", value=5.0, step=1.0)
        v_pes = c_r3.number_input("Pessimista (Rollouts/mês)", value=3.0, step=1.0)
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

# --- 3. MATRIZ DE ALOCAÇÃO (COM REATIVIDADE) ---
st.markdown('<div class="section-header">3. Matriz de Alocação e Orçamento</div>', unsafe_allow_html=True)
with st.container(border=True):
    m1, m2 = st.columns(2)
    data_inicio = m1.date_input("Início do Evento/Impacto", value=datetime.now(), format="DD/MM/YYYY")
    horizonte = m2.number_input("Meses (Horizonte)", min_value=1, value=1)
    lista_meses = get_meses_list(data_inicio, horizonte)

    with st.expander("➕ Adicionar Recurso ao Orçamento", expanded=False):
        f1, f2, f3 = st.columns(3)
        cargo = f1.selectbox("Cargo", ["Analista", "Consultor", "Especialista", "Gerente", "Desenvolvedor"])
        nivel = f2.selectbox("Nível", ["Junior", "Pleno", "Senior"])
        reg_cc = f3.selectbox("Regional",[" ", "Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"])
        f4, f5, f6 = st.columns(3)
        taxa_h = f4.number_input("Taxa/Hora(R$)", value=150.0)
        hrs_base = f5.number_input("Horas/Mês (Base)", value=160)
        
        if f6.button("ADICIONAR RECURSO"):
        if reg_cc.strip() == "":
        st.warning("Selecione uma Regional válida.")
    else:
        h_dist = {m: float(hrs_base) for m in lista_meses}
        total_r = sum(h_dist.values()) * taxa_h
        db_conn.execute(
            "INSERT INTO matriz_alocacao (projeto, cargo, nivel, reg, taxa, horas_json, total) VALUES (?,?,?,?,?,?,?)",
            (prog_nome, cargo, nivel, reg_cc, taxa_h, json.dumps(h_dist), total_r)
        )
        db_conn.commit()
        st.rerun()

    df_raw = pd.read_sql_query(f"SELECT * FROM matriz_alocacao WHERE projeto='{prog_nome}'", db_conn)

    if not df_raw.empty:
        df_edit = df_raw.copy()
        for mes in lista_meses:
            df_edit[mes] = df_edit['horas_json'].apply(lambda x: json.loads(x).get(mes, 0.0))
        
        cols_display = ['id', 'cargo', 'nivel', 'reg', 'taxa'] + lista_meses
        
        # EDITOR REATIVO
        edited_df = st.data_editor(
            df_edit[cols_display],
            column_config={
                "id": None,
                "taxa": st.column_config.NumberColumn("Taxa/Hora (R$)", format="R$ %.2f"),
                **{mes: st.column_config.NumberColumn(f"Hrs {mes}", min_value=0) for mes in lista_meses}
            },
            num_rows="dynamic",
            use_container_width=True,
            key="editor_matriz"
        )

        # CÁLCULO EM TEMPO REAL (Baseado no conteúdo do editor)
        # Multiplica taxa pelas colunas de meses para cada linha
        horas_editadas = edited_df[lista_meses].sum(axis=1)
        custo_base_total = (horas_editadas * edited_df['taxa']).sum()
        
        c_salvar, c_msg = st.columns([0.2, 0.8])
        if c_salvar.button("💾 SALVAR ALTERAÇÕES"):
            # Lógica de persistência (Delete/Update)
            ids_atuais = edited_df['id'].tolist()
            ids_originais = df_raw['id'].tolist()
            for idx in [i for i in ids_originais if i not in ids_atuais]:
                db_conn.execute(f"DELETE FROM matriz_alocacao WHERE id = {idx}")

            for _, row in edited_df.iterrows():
                h_json = json.dumps({mes: float(row[mes]) for mes in lista_meses})
                tot_linha = sum([float(row[mes]) for mes in lista_meses]) * row['taxa']
                db_conn.execute("UPDATE matriz_alocacao SET taxa=?, horas_json=?, total=? WHERE id=?", 
                             (row['taxa'], h_json, tot_linha, row['id']))
            db_conn.commit()
            st.rerun()
        c_msg.info("Os cálculos abaixo já refletem as edições da tabela em tempo real.")

    else:
        custo_base_total = 0.0
        st.info("Nenhum recurso alocado.")

# --- 4. RISCOS E 7. DRE (UNIDOS PARA REATIVIDADE) ---
st.markdown('<div class="section-header">4. Análise de Riscos e Orçamento Total</div>', unsafe_allow_html=True)
delta_pert_risco = 0.15 
reserva_risco = custo_base_total * delta_pert_risco
total_cenario = custo_base_total + reserva_risco

r1, r2, r3 = st.columns(3)
r1.metric("Custo Estimado (Baseline)", format_brl(custo_base_total))
r2.metric("Reserva de Risco (Delta PERT)", format_brl(reserva_risco))
r3.metric("Orçamento Total (Base + Risco)", format_brl(total_cenario))

st.markdown('<div class="section-header">7. DRE do Programa: Análise de margem final</div>', unsafe_allow_html=True)
with st.container(border=True):
    d1, d2, d3 = st.columns(3)
    margem_meta = d1.number_input("Margem inicial (Meta) %", value=45.0, step=1.0)
    receita_liq = d2.number_input("Receita líquida atual", min_value=1.0, value=5000.0, step=1000.0)
    custo_eac_atual = d3.number_input("Custo total atual (EAC)", min_value=1.0, value=1000.0, step=1000.0)

    # Cálculos reativos finais
    margem_atual = (1 - (custo_eac_atual/receita_liq)) * 100
    novo_eac = custo_eac_atual + total_cenario
    margem_final = (1 - (novo_eac/receita_liq)) * 100
    erosao = margem_atual - margem_final

    st.divider()
    res1, res2, res3 = st.columns(3)
    res1.metric("Margem atual", f"{margem_atual:.2f}%")
    with res2:
        metric_card_custom("Margem projetada total", f"{margem_final:.2f}%", erosao)
    res3.metric("Erosão de Margem", f"{erosao:.2f} p.p.")

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
st.markdown('<div class="section-header">6. Análise integrada</div>', unsafe_allow_html=True)
col_g1, col_g2 = st.columns([0.4, 0.6])
with col_g1:
    categories = ['Custo', 'Escopo', 'Tempo']
    fig_tri = go.Figure()

    # --- CAMADA: PLANEJADO (Ex: Azul Suave) ---
    fig_tri.add_trace(go.Scatterpolar(
        r=[80, 80, 80, 80], 
        theta=categories+['Custo'], 
        fill='toself', 
        name='Planejado',
        line_color='#1f77b4',  # Cor da linha
        fillcolor='rgba(31, 119, 180, 0.3)' # Cor do preenchimento com transparência
    ))

    # --- CAMADA: IMPACTO (Ex: Vermelho/Laranja Vibrante) ---
    fig_tri.add_trace(go.Scatterpolar(
        r=[100, 110, 120, 100], 
        theta=categories+['Custo'], 
        fill='toself', 
        name='Impacto',
        line_color='#d32f2f', # Cor da linha (Vermelho)
        fillcolor='rgba(211, 47, 47, 0.4)' # Cor do preenchimento com transparência
    ))

    fig_tri.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 150]) # Ativado para facilitar leitura
        ), 
        showlegend=True, 
        title="Tríplice de Restrição"
    )
    st.plotly_chart(fig_tri, use_container_width=True)

# --- BOTÃO SALVAR E GERAR PDF (TRECHO ATUALIZADO) ---
if st.sidebar.button("💾 SALVAR DADOS E GERAR PDF"):
    # 1. SALVAR NO BANCO SQL (Mantido igual)
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_conn.execute('''INSERT INTO resumo_impacto 
                       (data_geracao, projeto, custo_total, margem_antes, margem_depois, erosao) 
                       VALUES (?, ?, ?, ?, ?, ?)''', 
                    (agora, prog_nome, total_cenario, margem_atual, margem_final, erosao))
    db_conn.commit()

    # 2. GERAR PDF
    pdf = RelatorioExecutivo()
    pdf.add_page()
    
    # Capítulo 1: Identificação
    pdf.chapter_title("1. IDENTIFICACAO DO PROGRAMA")
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(40, 7, "Programa:"); pdf.set_font('Arial', '', 9); pdf.cell(0, 7, prog_nome, 0, 1)
    pdf.set_font('Arial', 'B', 9); pdf.cell(40, 7, "Responsavel:"); pdf.set_font('Arial', '', 9); pdf.cell(0, 7, prog_gerente, 0, 1)
    pdf.set_font('Arial', 'B', 9); pdf.cell(40, 7, "Contexto:"); pdf.ln(7)
    pdf.set_font('Arial', 'I', 9); pdf.multi_cell(0, 5, contexto)
    pdf.ln(5)

    # Capítulo 2: Matriz de Alocação
    pdf.chapter_title("2. DETALHAMENTO DA MATRIZ DE RECURSOS")
    pdf.set_font('Arial', 'B', 8)
    pdf.set_fill_color(0, 51, 102); pdf.set_text_color(255, 255, 255)
    pdf.cell(50, 7, "Cargo / Perfil", 1, 0, 'C', True)
    pdf.cell(40, 7, "Regional", 1, 0, 'C', True)
    pdf.cell(30, 7, "Taxa/Hora", 1, 0, 'C', True)
    pdf.cell(30, 7, "Horas Totais", 1, 0, 'C', True)
    pdf.cell(40, 7, "Total Bruto", 1, 1, 'C', True)
    
    pdf.set_font('Arial', '', 8); pdf.set_text_color(0, 0, 0)
    
    # Verificação de segurança caso o dataframe não tenha sido gerado
    if 'edited_df' in locals():
        for _, row in edited_df.iterrows():
            # Soma as horas de todas as colunas de meses da linha atual
            hrs_totais = sum([float(row[m]) for m in lista_meses])
            valor_total_recurso = hrs_totais * row['taxa']
            
            pdf.cell(50, 7, str(row['cargo']), 1)
            pdf.cell(40, 7, str(row['reg']), 1, 0, 'C')
            pdf.cell(30, 7, f"R$ {row['taxa']:.2f}", 1, 0, 'R')
            pdf.cell(30, 7, f"{hrs_totais:.1f}", 1, 0, 'C')
            pdf.cell(40, 7, format_brl(valor_total_recurso), 1, 1, 'R')
    else:
        pdf.cell(0, 7, "Nenhum recurso listado no cenário.", 1, 1, 'C')
    
    # Capítulo 3: Análise Financeira
    pdf.ln(5)
    pdf.chapter_title("3. ANALISE DE IMPACTO FINANCEIRO E RISCO")
    pdf.set_font('Arial', '', 9)
    pdf.cell(100, 7, "Subtotal Recursos Adicionais:", 0, 0); pdf.cell(0, 7, format_brl(custo_base_total), 0, 1, 'R')
    pdf.cell(100, 7, "Reserva de Risco (15% PERT):", 0, 0); pdf.cell(0, 7, format_brl(reserva_risco), 0, 1, 'R')
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(100, 10, "VALOR TOTAL DO IMPACTO (A):", 0, 0); pdf.cell(0, 10, format_brl(total_cenario), 0, 1, 'R')
    pdf.ln(5)

    # Capítulo 4: DRE e Margem
    pdf.chapter_title("4. IMPACTO NA MARGEM LIQUIDA (DRE)")
    pdf.set_font('Arial', '', 9)
    pdf.cell(100, 7, "Margem de Lucro Baseline (Antes):", 0, 0); pdf.cell(0, 7, f"{margem_atual:.2f}%", 0, 1, 'R')
    pdf.cell(100, 7, "Margem de Lucro Projetada (Depois):", 0, 0); pdf.cell(0, 7, f"{margem_final:.2f}%", 0, 1, 'R')
    pdf.set_font('Arial', 'B', 10); pdf.set_text_color(180, 0, 0)
    pdf.cell(100, 10, "EROSAO DE MARGEM DETECTADA:", 0, 0); pdf.cell(0, 10, f"{erosao:.2f} p.p.", 0, 1, 'R')
    
# --- CAPÍTULO 5: ANÁLISE GRÁFICA (COM TRATAMENTO DE ESPAÇO) ---
    # Verifica se os gráficos cabem na página (precisamos de aprox. 80mm)
    if pdf.get_y() > 180:
        pdf.add_page()

    pdf.chapter_title("5. ANALISE GRAFICA: MARGEM E TRIPLICE DE RESTRICAO")
    
    try:
        y_graficos = pdf.get_y() + 5
        largura_grafico = 80 
        
        # Gerar Histograma
        fig_hist, ax1 = plt.subplots(figsize=(5, 3.5))
        bars = ax1.bar(['Baseline', 'Projetado'], [margem_atual, margem_final], color=['#003366', '#d32f2f'])
        ax1.set_ylim(0, max(margem_atual, margem_final) + 20)
        ax1.set_title("Erosao de Margem %", fontsize=10, fontweight='bold')
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp1:
            plt.savefig(tmp1.name, format='png', bbox_inches='tight', dpi=150)
            pdf.image(tmp1.name, x=15, y=y_graficos, w=largura_grafico)
        plt.close(fig_hist)

        # Gerar Radar
        fig_radar = plt.figure(figsize=(5, 3.5))
        ax2 = fig_radar.add_subplot(111, polar=True)
        # ... (lógica do radar mantida)
        categorias = ['Custo', 'Escopo', 'Tempo']
        angles = np.linspace(0, 2 * np.pi, len(categorias), endpoint=False).tolist()
        angles += angles[:1]
        ax2.plot(angles, [80, 80, 80, 80], color='#1f77b4', linewidth=2)
        ax2.fill(angles, [80, 80, 80, 80], color='#1f77b4', alpha=0.2)
        ax2.plot(angles, [100, 110, 120, 100], color='#d32f2f', linewidth=2)
        ax2.fill(angles, [100, 110, 120, 100], color='#d32f2f', alpha=0.4)
        ax2.set_thetagrids(np.degrees(angles[:-1]), categorias)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp2:
            plt.savefig(tmp2.name, format='png', bbox_inches='tight', dpi=150)
            pdf.image(tmp2.name, x=110, y=y_graficos, w=largura_grafico)
        plt.close(fig_radar)

        # --- REPOSICIONAMENTO PÓS-GRÁFICOS ---
        # Definimos o Y abaixo da altura dos gráficos (y_graficos + altura da imagem)
        pdf.set_y(-65) 

    except Exception as e:
        st.error(f"Erro nos gráficos: {e}")

    # Conclusão Texto (Agora posicionado logo acima das assinaturas)
    pdf.set_font('Arial', 'B', 10)
    pdf.set_text_color(0, 51, 102) # Azul para combinar com o tema
    pdf.multi_cell(0, 7, f"Conclusao: O impacto total de {format_brl(total_cenario)} resultou em uma erosao de {erosao:.2f} p.p. na margem do programa.", 0, 'C')
    
    # Chama as assinaturas que estão fixas em set_y(-50)
    pdf.assinaturas()

    # Download
    output = pdf.output(dest='S')
    st.sidebar.download_button(
        label="📥 Baixar PDF Agora",
        data=bytes(output),
        file_name=f"Dossie_{prog_nome}.pdf",
        mime="application/pdf"
    )
