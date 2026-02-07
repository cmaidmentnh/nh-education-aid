from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Municipality(db.Model):
    __tablename__ = 'municipalities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False, unique=True)
    loc_id = db.Column(db.Integer)
    county = db.Column(db.Text)

    adequacy_records = db.relationship('AdequacyAid', backref='municipality', lazy='dynamic')
    sped_records = db.relationship('SpedAid', backref='municipality', lazy='dynamic')
    building_records = db.relationship('BuildingAid', backref='municipality', lazy='dynamic')
    cte_records = db.relationship('CTEAid', backref='municipality', lazy='dynamic')
    kindergarten_records = db.relationship('KindergartenAid', backref='municipality', lazy='dynamic')


class AdequacyAid(db.Model):
    __tablename__ = 'adequacy_aid'
    id = db.Column(db.Integer, primary_key=True)
    municipality_id = db.Column(db.Integer, db.ForeignKey('municipalities.id'), nullable=False)
    fiscal_year = db.Column(db.Integer, nullable=False)
    adm = db.Column(db.Float)
    base_adequacy_aid = db.Column(db.Float)
    fr_aid = db.Column(db.Float)
    sped_differentiated_aid = db.Column(db.Float)
    ell_aid = db.Column(db.Float)
    home_ed_aid = db.Column(db.Float)
    grade3_reading_aid = db.Column(db.Float)
    total_cost_adequate_ed = db.Column(db.Float)
    swept = db.Column(db.Float)
    extraordinary_needs_grant = db.Column(db.Float)
    hold_harmless_grant = db.Column(db.Float)
    fiscal_capacity_aid = db.Column(db.Float)
    stabilization_grant = db.Column(db.Float)
    total_adequacy_grant = db.Column(db.Float)
    total_state_grant = db.Column(db.Float)
    base_cost_per_pupil = db.Column(db.Float)
    swept_rate = db.Column(db.Float)
    fr_adm = db.Column(db.Float)
    sped_adm = db.Column(db.Float)
    ell_adm = db.Column(db.Float)

    __table_args__ = (db.UniqueConstraint('municipality_id', 'fiscal_year'),)


class SpedAid(db.Model):
    __tablename__ = 'sped_aid'
    id = db.Column(db.Integer, primary_key=True)
    municipality_id = db.Column(db.Integer, db.ForeignKey('municipalities.id'), nullable=False)
    fiscal_year = db.Column(db.Integer, nullable=False)
    num_students = db.Column(db.Integer)
    district_liability = db.Column(db.Float)
    cost_3_5_to_10x = db.Column(db.Float)
    num_students_over_10x = db.Column(db.Integer)
    cost_over_10x = db.Column(db.Float)
    total_district_cost = db.Column(db.Float)
    entitlement = db.Column(db.Float)
    appropriation = db.Column(db.Float)

    __table_args__ = (db.UniqueConstraint('municipality_id', 'fiscal_year'),)


class BuildingAid(db.Model):
    __tablename__ = 'building_aid'
    id = db.Column(db.Integer, primary_key=True)
    municipality_id = db.Column(db.Integer, db.ForeignKey('municipalities.id'), nullable=False)
    fiscal_year = db.Column(db.Integer, nullable=False)
    current_year_aid = db.Column(db.Float)
    prior_year_shortfall = db.Column(db.Float)
    total_entitlement = db.Column(db.Float)

    __table_args__ = (db.UniqueConstraint('municipality_id', 'fiscal_year'),)


class CharterSchoolAid(db.Model):
    __tablename__ = 'charter_school_aid'
    id = db.Column(db.Integer, primary_key=True)
    school_name = db.Column(db.Text, nullable=False)
    fiscal_year = db.Column(db.Integer, nullable=False)
    adm = db.Column(db.Float)
    per_pupil_rate = db.Column(db.Float)
    total_aid = db.Column(db.Float)
    fr_aid = db.Column(db.Float)
    sped_aid = db.Column(db.Float)
    ell_aid = db.Column(db.Float)

    __table_args__ = (db.UniqueConstraint('school_name', 'fiscal_year'),)


class CTEAid(db.Model):
    __tablename__ = 'cte_aid'
    id = db.Column(db.Integer, primary_key=True)
    municipality_id = db.Column(db.Integer, db.ForeignKey('municipalities.id'), nullable=False)
    fiscal_year = db.Column(db.Integer, nullable=False)
    tuition_payment = db.Column(db.Float)
    transportation_payment = db.Column(db.Float)
    total_payment = db.Column(db.Float)

    __table_args__ = (db.UniqueConstraint('municipality_id', 'fiscal_year'),)


class KindergartenAid(db.Model):
    __tablename__ = 'kindergarten_aid'
    id = db.Column(db.Integer, primary_key=True)
    municipality_id = db.Column(db.Integer, db.ForeignKey('municipalities.id'), nullable=False)
    fiscal_year = db.Column(db.Integer, nullable=False)
    adm = db.Column(db.Float)
    per_pupil_rate = db.Column(db.Float)
    total_aid = db.Column(db.Float)

    __table_args__ = (db.UniqueConstraint('municipality_id', 'fiscal_year'),)


class StatewideTotals(db.Model):
    __tablename__ = 'statewide_totals'
    fiscal_year = db.Column(db.Integer, primary_key=True)
    total_adequacy_aid = db.Column(db.Float)
    total_sped_aid = db.Column(db.Float)
    total_building_aid = db.Column(db.Float)
    total_charter_aid = db.Column(db.Float)
    total_cte_aid = db.Column(db.Float)
    total_kindergarten_aid = db.Column(db.Float)
    total_all_education_aid = db.Column(db.Float)
    base_cost_per_pupil = db.Column(db.Float)
    swept_rate = db.Column(db.Float)
    total_adm = db.Column(db.Float)
    total_fr_adm = db.Column(db.Float)
    aid_per_pupil = db.Column(db.Float)
