#!/usr/bin/env python3
"""NH Education Funding Facts - Flask Application"""

import os
from flask import Flask, render_template, jsonify, request, abort
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from models import db, Municipality, AdequacyAid, SpedAid, BuildingAid, \
    CharterSchoolAid, CTEAid, KindergartenAid, StatewideTotals

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-me-in-production')
default_db = 'sqlite:///' + os.path.join(basedir, 'education_aid.db')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', default_db)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


# ============================================================
# TEMPLATE HELPERS
# ============================================================

@app.template_filter('currency')
def currency_filter(value):
    """Format a number as currency."""
    if value is None:
        return '$0'
    if abs(value) >= 1_000_000_000:
        return f'${value / 1_000_000_000:,.1f}B'
    if abs(value) >= 1_000_000:
        return f'${value / 1_000_000:,.1f}M'
    if abs(value) >= 1_000:
        return f'${value / 1_000:,.0f}K'
    return f'${value:,.0f}'


@app.template_filter('currency_full')
def currency_full_filter(value):
    """Format as full dollar amount."""
    if value is None:
        return '$0'
    return f'${value:,.0f}'


@app.template_filter('pct_change')
def pct_change_filter(new, old):
    """Calculate percent change."""
    if not old or not new:
        return '0%'
    return f'{((new - old) / old) * 100:+.1f}%'


@app.context_processor
def utility_processor():
    return {
        'min_year': 2004,
        'max_year': 2027,
    }


# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def index():
    """Homepage with statewide dashboard."""
    totals = StatewideTotals.query.order_by(StatewideTotals.fiscal_year).all()
    years = [t.fiscal_year for t in totals]
    adequacy = [t.total_adequacy_aid or 0 for t in totals]
    sped = [t.total_sped_aid or 0 for t in totals]
    building = [t.total_building_aid or 0 for t in totals]
    charter = [t.total_charter_aid or 0 for t in totals]
    cte = [t.total_cte_aid or 0 for t in totals]
    kindergarten = [t.total_kindergarten_aid or 0 for t in totals]
    total_all = [t.total_all_education_aid or 0 for t in totals]
    per_pupil = [t.aid_per_pupil if t.aid_per_pupil and t.aid_per_pupil > 0 else None for t in totals]
    base_cost = [t.base_cost_per_pupil if t.base_cost_per_pupil and t.base_cost_per_pupil > 0 else None for t in totals]
    adm_data = [t.total_adm if t.total_adm and t.total_adm > 0 else None for t in totals]

    # Hero stats
    first = totals[0] if totals else None
    latest = totals[-1] if totals else None
    # Find the latest year with good total data
    latest_good = None
    for t in reversed(totals):
        if t.total_all_education_aid and t.total_all_education_aid > 0:
            latest_good = t
            break
    first_good = None
    for t in totals:
        if t.total_all_education_aid and t.total_all_education_aid > 0:
            first_good = t
            break

    # Growth % uses adequacy grants (legislature-controlled funding, not SWEPT)
    growth_pct = 0
    if first_good and latest_good and first_good.total_adequacy_aid and first_good.total_adequacy_aid > 0:
        growth_pct = ((latest_good.total_adequacy_aid - first_good.total_adequacy_aid)
                      / first_good.total_adequacy_aid) * 100

    return render_template('index.html',
                           totals=totals,
                           years=years,
                           adequacy=adequacy,
                           sped=sped,
                           building=building,
                           charter=charter,
                           cte=cte,
                           kindergarten=kindergarten,
                           total_all=total_all,
                           per_pupil=per_pupil,
                           base_cost=base_cost,
                           adm_data=adm_data,
                           first=first_good,
                           latest=latest_good,
                           growth_pct=growth_pct)


@app.route('/town/<name>')
def town_detail(name):
    """Town detail page with funding history."""
    muni = Municipality.query.filter(
        db.func.lower(Municipality.name) == name.lower()
    ).first_or_404()

    adequacy = AdequacyAid.query.filter_by(municipality_id=muni.id) \
        .order_by(AdequacyAid.fiscal_year).all()
    sped = SpedAid.query.filter_by(municipality_id=muni.id) \
        .order_by(SpedAid.fiscal_year).all()
    building = BuildingAid.query.filter_by(municipality_id=muni.id) \
        .order_by(BuildingAid.fiscal_year).all()
    cte = CTEAid.query.filter_by(municipality_id=muni.id) \
        .order_by(CTEAid.fiscal_year).all()
    kindergarten = KindergartenAid.query.filter_by(municipality_id=muni.id) \
        .order_by(KindergartenAid.fiscal_year).all()

    years = [a.fiscal_year for a in adequacy]
    grants = [a.total_adequacy_grant or 0 for a in adequacy]
    total_state = [a.total_state_grant or 0 for a in adequacy]
    adm_data = [a.adm if a.adm and a.adm > 0 else None for a in adequacy]
    swept_data = [a.swept or 0 for a in adequacy]

    # Calculate growth
    first_grant = next((a for a in adequacy if a.total_adequacy_grant and a.total_adequacy_grant > 0), None)
    last_grant = next((a for a in reversed(adequacy) if a.total_adequacy_grant and a.total_adequacy_grant > 0), None)
    growth_pct = 0
    if first_grant and last_grant and first_grant.total_adequacy_grant:
        growth_pct = ((last_grant.total_adequacy_grant - first_grant.total_adequacy_grant)
                      / first_grant.total_adequacy_grant) * 100

    # Per-pupil over time (uses total_state_grant which includes SWEPT)
    per_pupil = []
    for a in adequacy:
        if a.adm and a.adm > 0 and a.total_state_grant:
            per_pupil.append(round(a.total_state_grant / a.adm, 2))
        else:
            per_pupil.append(None)

    # Enrollment change
    first_adm = next((a for a in adequacy if a.adm and a.adm > 0), None)
    last_adm = next((a for a in reversed(adequacy) if a.adm and a.adm > 0), None)
    enrollment_change_pct = 0
    if first_adm and last_adm and first_adm.adm:
        enrollment_change_pct = ((last_adm.adm - first_adm.adm)
                                 / first_adm.adm) * 100

    # Per-pupil aid growth
    first_pp = next((pp for pp in per_pupil if pp and pp > 0), None)
    last_pp = next((pp for pp in reversed(per_pupil) if pp and pp > 0), None)
    per_pupil_growth_pct = 0
    if first_pp and last_pp:
        per_pupil_growth_pct = ((last_pp - first_pp) / first_pp) * 100

    return render_template('town.html',
                           muni=muni,
                           adequacy=adequacy,
                           sped=sped,
                           building=building,
                           cte=cte,
                           kindergarten=kindergarten,
                           years=years,
                           grants=grants,
                           total_state=total_state,
                           adm_data=adm_data,
                           swept_data=swept_data,
                           per_pupil=per_pupil,
                           growth_pct=growth_pct,
                           first_grant=first_grant,
                           last_grant=last_grant,
                           enrollment_change_pct=enrollment_change_pct,
                           first_adm=first_adm,
                           last_adm=last_adm,
                           per_pupil_growth_pct=per_pupil_growth_pct)


@app.route('/compare')
def compare():
    """Compare towns side by side."""
    town_names = request.args.getlist('towns')
    towns_data = []

    for name in town_names[:4]:  # Max 4 towns
        muni = Municipality.query.filter(
            db.func.lower(Municipality.name) == name.lower()
        ).first()
        if not muni:
            continue
        adequacy = AdequacyAid.query.filter_by(municipality_id=muni.id) \
            .order_by(AdequacyAid.fiscal_year).all()
        years = [a.fiscal_year for a in adequacy]
        grants = [a.total_adequacy_grant or 0 for a in adequacy]
        per_pupil = []
        for a in adequacy:
            if a.adm and a.adm > 0 and a.total_state_grant:
                per_pupil.append(round(a.total_state_grant / a.adm, 2))
            else:
                per_pupil.append(None)
        towns_data.append({
            'name': muni.name,
            'years': years,
            'grants': grants,
            'per_pupil': per_pupil,
        })

    return render_template('compare.html', towns_data=towns_data, town_names=town_names)


@app.route('/facts')
def facts():
    """Key facts and talking points page."""
    totals = StatewideTotals.query.order_by(StatewideTotals.fiscal_year).all()
    return render_template('facts.html', totals=totals)


@app.route('/data')
def data_page():
    """Data download page."""
    municipalities = Municipality.query.order_by(Municipality.name).all()
    years = db.session.query(AdequacyAid.fiscal_year).distinct() \
        .order_by(AdequacyAid.fiscal_year).all()
    years = [y[0] for y in years]
    return render_template('data.html', municipalities=municipalities, years=years)


# ============================================================
# API ENDPOINTS
# ============================================================

@app.route('/api/search')
def api_search():
    """Town search autocomplete."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    results = Municipality.query.filter(
        Municipality.name.ilike(f'%{q}%')
    ).order_by(Municipality.name).limit(10).all()
    return jsonify([{'name': m.name, 'id': m.id} for m in results])


@app.route('/api/town/<name>')
def api_town(name):
    """Town data as JSON."""
    muni = Municipality.query.filter(
        db.func.lower(Municipality.name) == name.lower()
    ).first()
    if not muni:
        return jsonify({'error': 'Town not found'}), 404

    adequacy = AdequacyAid.query.filter_by(municipality_id=muni.id) \
        .order_by(AdequacyAid.fiscal_year).all()

    return jsonify({
        'name': muni.name,
        'data': [{
            'fiscal_year': a.fiscal_year,
            'adm': a.adm,
            'total_adequacy_grant': a.total_adequacy_grant,
            'total_state_grant': a.total_state_grant,
            'swept': a.swept,
            'base_adequacy_aid': a.base_adequacy_aid,
            'fr_aid': a.fr_aid,
            'sped_differentiated_aid': a.sped_differentiated_aid,
            'ell_aid': a.ell_aid,
        } for a in adequacy]
    })


@app.route('/api/statewide')
def api_statewide():
    """Statewide totals as JSON."""
    totals = StatewideTotals.query.order_by(StatewideTotals.fiscal_year).all()
    return jsonify([{
        'fiscal_year': t.fiscal_year,
        'total_adequacy_aid': t.total_adequacy_aid,
        'total_sped_aid': t.total_sped_aid,
        'total_building_aid': t.total_building_aid,
        'total_charter_aid': t.total_charter_aid,
        'total_cte_aid': t.total_cte_aid,
        'total_kindergarten_aid': t.total_kindergarten_aid,
        'total_all_education_aid': t.total_all_education_aid,
        'base_cost_per_pupil': t.base_cost_per_pupil,
        'aid_per_pupil': t.aid_per_pupil,
        'total_adm': t.total_adm,
    } for t in totals])


@app.route('/api/export/<name>')
def api_export(name):
    """Export town data as CSV."""
    muni = Municipality.query.filter(
        db.func.lower(Municipality.name) == name.lower()
    ).first()
    if not muni:
        return jsonify({'error': 'Town not found'}), 404

    adequacy = AdequacyAid.query.filter_by(municipality_id=muni.id) \
        .order_by(AdequacyAid.fiscal_year).all()

    lines = ['Fiscal Year,ADM,Base Adequacy Aid,F&R Aid,SPED Aid,ELL Aid,Total Cost,SWEPT,Adequacy Grant,Total State Grant']
    for a in adequacy:
        lines.append(f'{a.fiscal_year},{a.adm or ""},{a.base_adequacy_aid or ""},{a.fr_aid or ""},'
                     f'{a.sped_differentiated_aid or ""},{a.ell_aid or ""},'
                     f'{a.total_cost_adequate_ed or ""},{a.swept or ""},'
                     f'{a.total_adequacy_grant or ""},{a.total_state_grant or ""}')

    from flask import Response
    return Response(
        '\n'.join(lines),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={muni.name}_education_aid.csv'}
    )


if __name__ == '__main__':
    app.run(debug=True, port=5010)
