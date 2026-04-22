"""
Dashboard de visualisation de la base historique AO Localizz.
Timeline des marchés, alertes de relance, analyse concurrentielle.

Usage:
    streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
from datetime import datetime, timedelta
from collections import Counter

st.set_page_config(
    page_title="Localizz - Suivi AO",
    page_icon="📊",
    layout="wide",
)

HISTORIQUE_PATH = os.path.join(os.path.dirname(__file__), "output", "historique_ao.json")


def categorize_lot(lot_name):
    """Catégorise un lot par mots-clés."""
    lot = lot_name.lower()
    categories = []
    keywords = {
        "Viande": ["viande", "bœuf", "buf", "veau", "porc", "agneau", "mouton", "boucherie"],
        "Volaille": ["volaille", "poulet", "dinde", "lapin"],
        "Charcuterie": ["charcuterie", "jambon", "salaison"],
        "Produits Laitiers": ["lait", "laitier", "fromage", "beurre", "œuf", "oeuf", "ovoproduit", "bof"],
        "Fruits & Légumes": ["fruit", "légume", "legume", "aromate", "pomme de terre", "pdt"],
        "Surgelés": ["surgelé", "surgele", "congelé"],
        "BIO": ["bio", "biologique"],
        "Épicerie": ["épicerie", "epicerie", "féculent", "pâte", "riz", "condiment", "épice", "conserve", "huile"],
        "Poisson": ["poisson", "halieutique", "crustacé", "mer"],
        "Boissons": ["boisson", "café", "thé"],
        "Boulangerie": ["pain", "viennoiserie", "boulangerie", "pâtisserie"],
        "4e/5e gamme": ["4e gamme", "5e gamme", "4ème gamme", "5ème gamme", "ivème", "vème"],
    }
    for cat, kws in keywords.items():
        if any(kw in lot for kw in kws):
            categories.append(cat)
    return categories if categories else ["Autre"]


@st.cache_data
def load_data():
    """Charge et prépare les données."""
    if not os.path.exists(HISTORIQUE_PATH):
        st.error(f"Base historique non trouvée: {HISTORIQUE_PATH}")
        st.info("Lancez d'abord: `python3 scripts/build_historique.py`")
        return pd.DataFrame()

    with open(HISTORIQUE_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    records = []
    for item in raw:
        date_debut = item.get("date_debut")
        date_fin = item.get("date_fin")

        try:
            dt_debut = pd.to_datetime(date_debut) if date_debut else None
            dt_fin = pd.to_datetime(date_fin) if date_fin else None
        except Exception:
            continue

        today = pd.Timestamp.now()
        if dt_fin:
            days_left = (dt_fin - today).days
            if days_left < 0:
                status = "Expiré"
            elif days_left <= 90:
                status = "Urgent"
            elif days_left <= 180:
                status = "Proche"
            elif days_left <= 365:
                status = "À surveiller"
            else:
                status = "En cours"
        else:
            days_left = None
            status = "Inconnu"

        titulaires = item.get("titulaire", [])
        tit_str = ", ".join(titulaires[:5]) if titulaires else ""
        departments = item.get("code_departement", [])
        lots = item.get("LOTS", [])

        all_categories = set()
        for lot in lots:
            all_categories.update(categorize_lot(lot))

        # Localizz est titulaire ?
        is_localizz = any(
            "localizz" in t.lower() or "pldp" in t.lower()
            for t in titulaires
        )

        records.append({
            "idweb": item.get("idweb", ""),
            "Objet": item.get("objet", "")[:120],
            "Objet_complet": item.get("objet", ""),
            "Acheteur": item.get("nomacheteur", ""),
            "Start": dt_debut,
            "Finish": dt_fin,
            "Date_parution": item.get("dateparution", ""),
            "Départements": departments,
            "Dept_str": ", ".join(str(d) for d in departments),
            "Titulaires": titulaires,
            "Titulaire_str": tit_str,
            "Lots": lots,
            "Nb_lots": len(lots),
            "Catégories": list(all_categories),
            "Status": status,
            "Days_left": days_left,
            "Durée_mois": item.get("Duree_totale_mois"),
            "Montant_HT": item.get("montant_total_ht"),
            "URL": item.get("url_avis", ""),
            "Localizz": is_localizz,
            "Reconduction": item.get("reconduction_description", ""),
        })

    return pd.DataFrame(records)


def render_timeline(df):
    """Affiche la timeline Gantt des marchés."""
    df_plot = df.dropna(subset=["Start", "Finish"]).copy()
    if df_plot.empty:
        st.warning("Aucun marché avec dates de début/fin pour la timeline.")
        return

    # Label court pour le Gantt — ajouter idweb pour dédupliquer les noms identiques
    df_plot["Label"] = df_plot["Acheteur"].str[:40] + " — " + df_plot["Objet"].str[:35] + " [" + df_plot["idweb"] + "]"

    fig = px.timeline(
        df_plot,
        x_start="Start",
        x_end="Finish",
        y="Label",
        color="Status",
        color_discrete_map={
            "Expiré": "#bdc3c7",
            "Urgent": "#e74c3c",
            "Proche": "#e67e22",
            "À surveiller": "#f1c40f",
            "En cours": "#2ecc71",
            "Inconnu": "#95a5a6",
        },
        hover_data=["Acheteur", "Titulaire_str", "Dept_str", "Days_left"],
    )

    # Ligne aujourd'hui
    today = datetime.now()
    fig.add_vline(x=today.strftime("%Y-%m-%d"), line_dash="dash", line_color="red", line_width=2)
    fig.add_annotation(
        x=today.strftime("%Y-%m-%d"), y=1.02, text="Aujourd'hui",
        showarrow=False, yref="paper", font=dict(color="red", size=12),
    )

    fig.update_layout(
        height=max(400, len(df_plot) * 28),
        yaxis_title="",
        xaxis_title="",
        showlegend=True,
        legend_title="Statut",
        margin=dict(l=10),
    )

    # Zoom par défaut: -6 mois à +18 mois
    fig.update_xaxes(
        range=[
            (today - timedelta(days=180)).strftime("%Y-%m-%d"),
            (today + timedelta(days=540)).strftime("%Y-%m-%d"),
        ]
    )

    st.plotly_chart(fig, use_container_width=True)


def render_relance_cards(df):
    """Affiche les cartes de relance urgentes."""
    today = pd.Timestamp.now()
    relances = df[df["Status"].isin(["Expiré", "Urgent", "Proche"])].sort_values("Days_left")

    if relances.empty:
        st.success("Aucune relance urgente pour le moment.")
        return

    for _, row in relances.iterrows():
        dl = row["Days_left"]
        if dl is None:
            continue
        if dl < 0:
            color = "#e74c3c"
            badge = f"EXPIRÉ ({abs(dl)}j)"
        elif dl <= 90:
            color = "#e67e22"
            badge = f"URGENT ({dl}j)"
        else:
            color = "#f1c40f"
            badge = f"PROCHE ({dl}j)"

        tits = ", ".join(row["Titulaires"][:3]) if row["Titulaires"] else "Non renseigné"
        lots_str = ", ".join(row["Lots"][:3]) if row["Lots"] else "Non renseigné"
        is_lz = " 🟢 LOCALIZZ" if row["Localizz"] else ""

        st.markdown(
            f"""<div style="border-left:4px solid {color};padding:10px 15px;margin-bottom:10px;
            background:#fafafa;border-radius:0 6px 6px 0;">
            <div style="display:flex;justify-content:space-between;">
                <strong>{row['Acheteur']}{is_lz}</strong>
                <span style="background:{color};color:white;padding:2px 8px;border-radius:3px;
                font-size:11px;font-weight:bold;">{badge}</span>
            </div>
            <div style="font-size:13px;color:#555;margin-top:5px;">
                <strong>Fin :</strong> {row['Finish'].strftime('%d/%m/%Y') if pd.notna(row['Finish']) else '?'}
                | <strong>Dept :</strong> {row['Dept_str']}
                | <strong>Titulaire(s) :</strong> {tits}<br>
                <strong>Lots :</strong> {lots_str}<br>
                <a href="{row['URL']}" target="_blank">Voir sur BOAMP</a>
            </div></div>""",
            unsafe_allow_html=True,
        )


def render_concurrence(df):
    """Analyse concurrentielle: quels fournisseurs dominent."""
    all_tits = []
    for tits in df["Titulaires"]:
        for t in tits:
            # Normaliser les noms
            name = t.strip().upper()
            # Regrouper les variantes
            for group, variants in {
                "SYSCO / BRAKE": ["SYSCO", "BRAKE"],
                "POMONA PASSION FROID": ["PASSION FROID", "PASSIONFROID"],
                "POMONA TERRE AZUR": ["TERRE AZUR", "TERREAZUR"],
                "POMONA EPISAVEURS": ["EPISAVEURS", "EPI SAVEURS"],
                "PRO A PRO": ["PRO A PRO"],
                "TRANSGOURMET": ["TRANSGOURMET"],
                "FELIX POTIN": ["FELIX POTIN"],
                "NATURDIS": ["NATURDIS"],
                "BIGARD / SOCOPA": ["BIGARD", "SOCOPA"],
                "LOCALIZZ / PLDP": ["LOCALIZZ", "PLDP"],
            }.items():
                if any(v in name for v in variants):
                    name = group
                    break
            all_tits.append(name)

    counter = Counter(all_tits)
    top = counter.most_common(15)

    if not top:
        return

    df_tits = pd.DataFrame(top, columns=["Fournisseur", "Nb marchés"])

    # Mettre Localizz en surbrillance
    colors = ["#e74c3c" if "LOCALIZZ" in f else "#3498db" for f in df_tits["Fournisseur"]]

    fig = go.Figure(go.Bar(
        x=df_tits["Nb marchés"],
        y=df_tits["Fournisseur"],
        orientation="h",
        marker_color=colors,
        text=df_tits["Nb marchés"],
        textposition="outside",
    ))
    fig.update_layout(
        height=450,
        yaxis=dict(autorange="reversed"),
        xaxis_title="Nombre de marchés remportés",
        margin=dict(l=10),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_categories(df):
    """Répartition par catégorie de produits."""
    all_cats = []
    for cats in df["Catégories"]:
        all_cats.extend(cats)

    counter = Counter(all_cats)
    df_cats = pd.DataFrame(counter.most_common(15), columns=["Catégorie", "Nb marchés"])

    fig = px.bar(df_cats, x="Catégorie", y="Nb marchés", color="Catégorie")
    fig.update_layout(showlegend=False, height=350)
    st.plotly_chart(fig, use_container_width=True)


def render_departements(df):
    """Répartition par département."""
    all_depts = []
    for depts in df["Départements"]:
        all_depts.extend(str(d) for d in depts)

    counter = Counter(all_depts)
    # Garder seulement PACA
    paca = {d: counter.get(d, 0) for d in ["04", "05", "06", "13", "83", "84"]}
    dept_names = {
        "04": "04 - Alpes-de-Haute-Provence",
        "05": "05 - Hautes-Alpes",
        "06": "06 - Alpes-Maritimes",
        "13": "13 - Bouches-du-Rhône",
        "83": "83 - Var",
        "84": "84 - Vaucluse",
    }

    df_dept = pd.DataFrame([
        {"Département": dept_names.get(d, d), "Nb marchés": v}
        for d, v in sorted(paca.items())
    ])

    fig = px.bar(df_dept, x="Département", y="Nb marchés", color="Département")
    fig.update_layout(showlegend=False, height=350)
    st.plotly_chart(fig, use_container_width=True)


def render_expiration_calendar(df):
    """Calendrier des expirations par mois."""
    df_exp = df.dropna(subset=["Finish"]).copy()
    df_exp = df_exp[df_exp["Finish"] >= pd.Timestamp.now() - timedelta(days=90)]
    df_exp = df_exp[df_exp["Finish"] <= pd.Timestamp.now() + timedelta(days=730)]

    if df_exp.empty:
        return

    df_exp["Mois_fin"] = df_exp["Finish"].dt.to_period("M").astype(str)
    monthly = df_exp.groupby("Mois_fin").size().reset_index(name="Nb expirations")

    fig = px.bar(
        monthly, x="Mois_fin", y="Nb expirations",
        title="Expirations de marchés par mois",
        labels={"Mois_fin": "Mois", "Nb expirations": "Nombre"},
    )

    # Ligne rouge pour aujourd'hui
    today_str = datetime.now().strftime("%Y-%m")
    fig.add_vline(x=today_str, line_dash="dash", line_color="red")
    fig.update_layout(height=300)
    st.plotly_chart(fig, use_container_width=True)


# ======== MAIN ========

def main():
    st.title("📊 Localizz — Suivi des Appels d'Offres")
    st.caption(f"Base: {HISTORIQUE_PATH} | Dernière mise à jour: voir date du fichier")

    df = load_data()
    if df.empty:
        return

    # === FILTRES ===
    with st.expander("🔍 Filtres", expanded=True):
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            acheteurs = sorted(df["Acheteur"].unique())
            sel_acheteurs = st.multiselect("Acheteur", acheteurs)

        with col2:
            all_depts = sorted(set(d for depts in df["Départements"] for d in depts))
            sel_depts = st.multiselect("Département", all_depts)

        with col3:
            all_cats = sorted(set(c for cats in df["Catégories"] for c in cats))
            sel_cats = st.multiselect("Catégorie produit", all_cats)

        with col4:
            statuses = ["Expiré", "Urgent", "Proche", "À surveiller", "En cours", "Inconnu"]
            sel_status = st.multiselect("Statut", statuses, default=["Urgent", "Proche", "À surveiller", "En cours"])

        with col5:
            sel_localizz = st.checkbox("Marchés Localizz uniquement")

    # Appliquer filtres
    filtered = df.copy()
    if sel_acheteurs:
        filtered = filtered[filtered["Acheteur"].isin(sel_acheteurs)]
    if sel_depts:
        filtered = filtered[filtered["Départements"].apply(lambda x: any(d in sel_depts for d in x))]
    if sel_cats:
        filtered = filtered[filtered["Catégories"].apply(lambda x: any(c in sel_cats for c in x))]
    if sel_status:
        filtered = filtered[filtered["Status"].isin(sel_status)]
    if sel_localizz:
        filtered = filtered[filtered["Localizz"]]

    # === MÉTRIQUES ===
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total AO", len(filtered))
    with col2:
        st.metric("En cours", len(filtered[filtered["Status"] == "En cours"]))
    with col3:
        urgent = len(filtered[filtered["Status"].isin(["Urgent", "Expiré"])])
        st.metric("Urgents / Expirés", urgent)
    with col4:
        lz = len(filtered[filtered["Localizz"]])
        st.metric("Marchés Localizz", lz)
    with col5:
        montant = filtered["Montant_HT"].sum()
        if montant > 0:
            st.metric("Montant total", f"{montant:,.0f} €")
        else:
            st.metric("Montant total", "N/A")

    # === ONGLETS ===
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📅 Timeline", "🔔 Relances", "🏢 Concurrence", "📦 Catégories", "📋 Données"
    ])

    with tab1:
        st.subheader("Timeline des marchés")
        render_timeline(filtered)
        render_expiration_calendar(filtered)

    with tab2:
        st.subheader("Relances à prévoir")
        st.markdown("Marchés arrivant à expiration — opportunités de prise de contact en amont.")
        render_relance_cards(filtered)

    with tab3:
        st.subheader("Analyse concurrentielle")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Top fournisseurs par nombre de marchés**")
            render_concurrence(filtered)
        with col_b:
            st.markdown("**Répartition par département**")
            render_departements(filtered)

    with tab4:
        st.subheader("Répartition par catégorie de produits")
        render_categories(filtered)

    with tab5:
        st.subheader("Données brutes")

        # Table avec les colonnes clés
        display_cols = [
            "Acheteur", "Objet", "Dept_str", "Status", "Days_left",
            "Titulaire_str", "Nb_lots", "Durée_mois", "Montant_HT",
            "Start", "Finish", "Localizz", "URL",
        ]
        display_df = filtered[display_cols].copy()
        display_df.columns = [
            "Acheteur", "Objet", "Depts", "Statut", "Jours restants",
            "Titulaires", "Nb lots", "Durée (mois)", "Montant HT",
            "Début", "Fin", "Localizz", "URL",
        ]

        st.dataframe(
            display_df.sort_values("Jours restants", na_position="last"),
            use_container_width=True,
            height=600,
            column_config={
                "URL": st.column_config.LinkColumn("BOAMP"),
                "Montant HT": st.column_config.NumberColumn(format="%.0f €"),
            },
        )


if __name__ == "__main__":
    main()
