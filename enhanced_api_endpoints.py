"""
Enhanced Presentation Export API Endpoints
Handles scheduling, branding, and advanced PPTX generation
"""

import sqlite3
import json
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

# This will be added to report_generator.py

def _get_db_connection():
    """Get database connection."""
    from .models import get_db
    return get_db()

@report_bp.route('/api/reports/presentation/advanced', methods=['POST'])
@jwt_required()
def export_presentation_advanced():
    """Export enhanced PPTX with all Phase 1 features."""
    try:
        user_id = get_jwt_identity()
        payload = request.get_json(silent=True) or {}
        
        year = int(payload.get('year', datetime.now().year))
        template_theme = str(payload.get('template_theme', 'corporate')).lower()
        export_format = str(payload.get('export_format', 'pptx')).lower()
        
        # Branding options
        org_name = payload.get('organization_name', '')
        logo_url = payload.get('logo_url', '')
        primary_color = payload.get('primary_color', '#667eea')
        watermark = payload.get('watermark', '')
        footer_text = payload.get('footer_text', '')
        
        # Content options
        include_toc = payload.get('include_toc', True)
        include_tables = payload.get('include_tables', True)
        include_appendix = payload.get('include_appendix', False)
        include_notes = payload.get('include_speaker_notes', True)
        include_qr = payload.get('include_qr_code', False)
        
        # Analytics options
        include_sentiment_trends = payload.get('include_sentiment_trends', True)
        include_growth_analysis = payload.get('include_growth_analysis', True)
        include_anomaly_details = payload.get('include_anomaly_details', True)
        include_key_metrics = payload.get('include_key_metrics_callout', True)
        include_recs = payload.get('include_prioritized_recommendations', True)
        
        # Visual options
        include_gradients = payload.get('include_background_gradient', True)
        high_contrast = payload.get('high_contrast_mode', False)
        enable_transitions = payload.get('enable_transitions', False)
        
        # Get base summary data
        from . import report_generator as rg
        data = rg._build_summary_payload(year=year, limit=8)
        
        # Build enhanced PPTX
        pptx_stream = rg._build_presentation_bytes(
            data=data,
            template_theme=template_theme,
            include_anomalies=include_anomaly_details,
            include_speaker_notes=include_notes,
            title=org_name or None,
            options={
                'include_toc': include_toc,
                'include_tables': include_tables,
                'include_appendix': include_appendix,
                'include_sentiment_trends': include_sentiment_trends,
                'include_growth_analysis': include_growth_analysis,
                'include_key_metrics': include_key_metrics,
                'include_prioritized_recs': include_recs,
                'include_qr_code': include_qr,
                'branding': {
                    'organization_name': org_name,
                    'logo_url': logo_url,
                    'primary_color': primary_color,
                    'watermark': watermark,
                    'footer_text': footer_text,
                },
                'visual': {
                    'include_gradients': include_gradients,
                    'high_contrast': high_contrast,
                    'enable_transitions': enable_transitions,
                }
            }
        )
        
        safe_theme = template_theme if template_theme in rg.PRESENTATION_THEME_STYLES else 'corporate'
        filename = f"governance-presentation-{year}-{safe_theme}.pptx"
        
        return send_file(
            pptx_stream,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )
        
    except Exception as e:
        logger.error(f"Enhanced PPTX export error: {e}")
        return jsonify({'error': 'Failed to generate enhanced presentation'}), 500


@report_bp.route('/api/reports/schedule', methods=['POST'])
@jwt_required()
def create_scheduled_report():
    """Create a scheduled report for recurring delivery."""
    try:
        user_id = get_jwt_identity()
        payload = request.get_json(silent=True) or {}
        
        report_name = payload.get('report_name', 'Automated Report')
        email_recipients = payload.get('email_recipients', [])
        frequency = payload.get('frequency', 'monthly')
        send_time = payload.get('send_time', '09:00')
        template_theme = payload.get('template_theme', 'corporate')
        year = payload.get('year', datetime.now().year)
        
        if not email_recipients:
            return jsonify({'error': 'At least one email recipient is required'}), 400
        
        conn = _get_db_connection()
        cursor = conn.cursor()
        
        recipients_str = ','.join(email_recipients) if isinstance(email_recipients, list) else email_recipients
        
        cursor.execute('''
            INSERT INTO ScheduledReports 
            (user_id, report_name, email_recipients, frequency, send_time, template_theme, year)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, report_name, recipients_str, frequency, send_time, template_theme, year))
        
        conn.commit()
        schedule_id = cursor.lastrowid
        conn.close()
        
        return jsonify({
            'status': 'scheduled',
            'id': schedule_id,
            'message': f'Report scheduled for {frequency} delivery'
        }), 201
        
    except Exception as e:
        logger.error(f"Schedule creation error: {e}")
        return jsonify({'error': 'Failed to create scheduled report'}), 500


@report_bp.route('/api/reports/schedule', methods=['GET'])
@jwt_required()
def get_scheduled_reports():
    """Get all scheduled reports for the current user."""
    try:
        user_id = get_jwt_identity()
        
        conn = _get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, report_name, email_recipients, frequency, send_time, 
                   template_theme, year, is_active, next_send
            FROM ScheduledReports
            WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        schedules = []
        for row in rows:
            schedules.append({
                'id': row[0],
                'report_name': row[1],
                'email_recipients': row[2].split(','),
                'frequency': row[3],
                'send_time': row[4],
                'template_theme': row[5],
                'year': row[6],
                'is_active': bool(row[7]),
                'next_send': row[8]
            })
        
        return jsonify(schedules), 200
        
    except Exception as e:
        logger.error(f"Get schedules error: {e}")
        return jsonify({'error': 'Failed to retrieve scheduled reports'}), 500


@report_bp.route('/api/reports/schedule/<int:schedule_id>', methods=['PUT'])
@jwt_required()
def update_scheduled_report(schedule_id):
    """Update a scheduled report."""
    try:
        user_id = get_jwt_identity()
        payload = request.get_json(silent=True) or {}
        
        conn = _get_db_connection()
        cursor = conn.cursor()
        
        # Verify ownership
        cursor.execute('SELECT user_id FROM ScheduledReports WHERE id = ?', (schedule_id,))
        result = cursor.fetchone()
        if not result or result[0] != user_id:
            conn.close()
            return jsonify({'error': 'Not found or unauthorized'}), 404
        
        updates = []
        params = []
        
        if 'report_name' in payload:
            updates.append('report_name = ?')
            params.append(payload['report_name'])
        
        if 'email_recipients' in payload:
            recipients = payload['email_recipients']
            recipients_str = ','.join(recipients) if isinstance(recipients, list) else recipients
            updates.append('email_recipients = ?')
            params.append(recipients_str)
        
        if 'frequency' in payload:
            updates.append('frequency = ?')
            params.append(payload['frequency'])
        
        if 'send_time' in payload:
            updates.append('send_time = ?')
            params.append(payload['send_time'])
        
        if 'is_active' in payload:
            updates.append('is_active = ?')
            params.append(int(payload['is_active']))
        
        if updates:
            updates.append('updated_at = CURRENT_TIMESTAMP')
            params.append(schedule_id)
            
            query = f"UPDATE ScheduledReports SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()
        
        conn.close()
        
        return jsonify({'status': 'updated', 'id': schedule_id}), 200
        
    except Exception as e:
        logger.error(f"Update schedule error: {e}")
        return jsonify({'error': 'Failed to update schedule'}), 500


@report_bp.route('/api/reports/schedule/<int:schedule_id>', methods=['DELETE'])
@jwt_required()
def delete_scheduled_report(schedule_id):
    """Delete a scheduled report."""
    try:
        user_id = get_jwt_identity()
        
        conn = _get_db_connection()
        cursor = conn.cursor()
        
        # Verify ownership
        cursor.execute('SELECT user_id FROM ScheduledReports WHERE id = ?', (schedule_id,))
        result = cursor.fetchone()
        if not result or result[0] != user_id:
            conn.close()
            return jsonify({'error': 'Not found or unauthorized'}), 404
        
        cursor.execute('DELETE FROM ScheduledReports WHERE id = ?', (schedule_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'deleted', 'id': schedule_id}), 200
        
    except Exception as e:
        logger.error(f"Delete schedule error: {e}")
        return jsonify({'error': 'Failed to delete schedule'}), 500


@report_bp.route('/api/reports/sentiment-trends/<int:year>', methods=['GET'])
@jwt_required()
def get_sentiment_trends(year):
    """Get monthly sentiment trends for a year."""
    try:
        query = '''
            SELECT 
                strftime('%m', tm.created_at) as month,
                ROUND(AVG(CASE WHEN a.sentiment = 'positive' THEN 1 ELSE 0 END) * 100, 1) as positive_rate,
                ROUND(AVG(CASE WHEN a.sentiment = 'neutral' THEN 1 ELSE 0 END) * 100, 1) as neutral_rate,
                ROUND(AVG(CASE WHEN a.sentiment = 'negative' THEN 1 ELSE 0 END) * 100, 1) as negative_rate
            FROM Meetings m
            LEFT JOIN TranscriptMetadata tm ON m.id = tm.meeting_id
            LEFT JOIN SentimentAnalysis a ON tm.id = a.metadata_id
            WHERE strftime('%Y', m.meeting_date) = ?
            GROUP BY strftime('%m', tm.created_at)
            ORDER BY month
        '''
        
        rows = execute_safe_query(query, (str(year),), fetch='all')
        
        trends = []
        for row in rows:
            trends.append({
                'month': int(row[0]) if row[0] else None,
                'positive_rate': row[1] or 0,
                'neutral_rate': row[2] or 0,
                'negative_rate': row[3] or 0,
            })
        
        return jsonify(trends), 200
        
    except Exception as e:
        logger.error(f"Sentiment trends error: {e}")
        return jsonify({'error': 'Failed to retrieve sentiment trends'}), 500


@report_bp.route('/api/reports/growth-analysis/<int:year>', methods=['GET'])
@jwt_required()
def get_growth_analysis(year):
    """Get theme growth analysis (YoY comparison)."""
    try:
        current_year_query = '''
            SELECT ta.theme_id, COUNT(*) as mentions
            FROM ThemeAnalysis ta
            JOIN Meetings m ON ta.meeting_id = m.id
            WHERE strftime('%Y', m.meeting_date) = ?
            GROUP BY ta.theme_id
        '''
        
        prev_year = year - 1
        prev_year_query = '''
            SELECT ta.theme_id, COUNT(*) as mentions
            FROM ThemeAnalysis ta
            JOIN Meetings m ON ta.meeting_id = m.id
            WHERE strftime('%Y', m.meeting_date) = ?
            GROUP BY ta.theme_id
        '''
        
        current_rows = execute_safe_query(current_year_query, (str(year),), fetch='all')
        prev_rows = execute_safe_query(prev_year_query, (str(prev_year),), fetch='all')
        
        current_data = {row[0]: row[1] for row in current_rows}
        prev_data = {row[0]: row[1] for row in prev_rows}
        
        growth_data = []
        for theme_id, current_mentions in current_data.items():
            prev_mentions = prev_data.get(theme_id, 0)
            growth_pct = (((current_mentions - prev_mentions) / prev_mentions * 100) 
                         if prev_mentions > 0 else (100 if current_mentions > 0 else 0))
            
            trend = '↑' if growth_pct > 10 else ('↓' if growth_pct < -10 else '→')
            
            growth_data.append({
                'theme_id': theme_id,
                'current': current_mentions,
                'previous': prev_mentions,
                'growth_pct': round(growth_pct, 1),
                'trend': trend
            })
        
        # Sort by growth percentage
        growth_data.sort(key=lambda x: x['growth_pct'], reverse=True)
        
        return jsonify(growth_data[:10]), 200
        
    except Exception as e:
        logger.error(f"Growth analysis error: {e}")
        return jsonify({'error': 'Failed to retrieve growth analysis'}), 500


@report_bp.route('/api/reports/anomalies-detailed/<int:year>', methods=['GET'])
@jwt_required()
def get_anomalies_detailed(year):
    """Get detailed anomaly information."""
    try:
        query = '''
            SELECT 
                ta.theme_id,
                a.month,
                a.mention_count,
                a.baseline,
                a.z_score,
                a.severity
            FROM Anomalies a
            LEFT JOIN ThemeAnalysis ta ON a.theme_id = ta.theme_id
            WHERE a.year = ?
            ORDER BY a.severity DESC, a.z_score DESC
            LIMIT 20
        '''
        
        rows = execute_safe_query(query, (year,), fetch='all')
        
        anomalies = []
        for row in rows:
            anomalies.append({
                'theme_id': row[0],
                'month': row[1],
                'mentions': row[2] or 0,
                'baseline': row[3] or 0,
                'z_score': row[4] or 0,
                'severity': row[5] or 'Low'
            })
        
        return jsonify(anomalies), 200
        
    except Exception as e:
        logger.error(f"Anomalies detailed error: {e}")
        return jsonify({'error': 'Failed to retrieve anomalies'}), 500


@report_bp.route('/api/reports/branding', methods=['GET'])
@jwt_required()
def get_branding():
    """Get user's branding settings."""
    try:
        user_id = get_jwt_identity()
        
        conn = _get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT organization_name, logo_url, primary_color, secondary_color,
                   accent_color, watermark, footer_text
            FROM PresentationBranding
            WHERE user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return jsonify({
                'organization_name': row[0],
                'logo_url': row[1],
                'primary_color': row[2],
                'secondary_color': row[3],
                'accent_color': row[4],
                'watermark': row[5],
                'footer_text': row[6]
            }), 200
        else:
            return jsonify({
                'organization_name': '',
                'logo_url': '',
                'primary_color': '#667eea',
                'secondary_color': '#764ba2',
                'accent_color': '#f59e0b',
                'watermark': '',
                'footer_text': ''
            }), 200
        
    except Exception as e:
        logger.error(f"Get branding error: {e}")
        return jsonify({'error': 'Failed to retrieve branding'}), 500


@report_bp.route('/api/reports/branding', methods=['PUT'])
@jwt_required()
def update_branding():
    """Update user's branding settings."""
    try:
        user_id = get_jwt_identity()
        payload = request.get_json(silent=True) or {}
        
        conn = _get_db_connection()
        cursor = conn.cursor()
        
        # Check if branding exists
        cursor.execute('SELECT id FROM PresentationBranding WHERE user_id = ?', (user_id,))
        exists = cursor.fetchone() is not None
        
        if exists:
            cursor.execute('''
                UPDATE PresentationBranding
                SET organization_name = ?,
                    logo_url = ?,
                    primary_color = ?,
                    secondary_color = ?,
                    accent_color = ?,
                    watermark = ?,
                    footer_text = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (
                payload.get('organization_name', ''),
                payload.get('logo_url', ''),
                payload.get('primary_color', '#667eea'),
                payload.get('secondary_color', '#764ba2'),
                payload.get('accent_color', '#f59e0b'),
                payload.get('watermark', ''),
                payload.get('footer_text', ''),
                user_id
            ))
        else:
            cursor.execute('''
                INSERT INTO PresentationBranding
                (user_id, organization_name, logo_url, primary_color, secondary_color, accent_color, watermark, footer_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                payload.get('organization_name', ''),
                payload.get('logo_url', ''),
                payload.get('primary_color', '#667eea'),
                payload.get('secondary_color', '#764ba2'),
                payload.get('accent_color', '#f59e0b'),
                payload.get('watermark', ''),
                payload.get('footer_text', '')
            ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'updated'}), 200
        
    except Exception as e:
        logger.error(f"Update branding error: {e}")
        return jsonify({'error': 'Failed to update branding'}), 500
