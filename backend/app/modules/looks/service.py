from app.modules.catalog.queries import PLAN_FROM, PLAN_SELECT, PUBLIC_PLAN
from app.modules.catalog.rules import validate_selection, generation_matches_outfit
from app.modules.catalog.schemas import Asset, Plan
from app.modules.looks.schemas import Look
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from uuid import UUID, uuid4
import psycopg


def missing():
    raise HTTPException(404, {'code': 'LOOK_NOT_FOUND', 'message': '找不到這筆收藏。'})


def conflict(message='收藏已在其他頁面更新，請重新載入後再確認。'):
    raise HTTPException(409, {'code': 'LOOK_CONFLICT', 'message': message})


def hydrate(rows, connection):
    if not rows:
        return []
    plans = connection.execute(PLAN_SELECT + PLAN_FROM + ' WHERE ' + PUBLIC_PLAN + ' AND p.id = ANY(%s)',
                               ([row['plan_id'] for row in rows],)).fetchall()
    by_id = {row['id']: Plan.model_validate(row) for row in plans}
    ids = list({UUID(str(value)) for row in rows for value in [row.get('generation_id'),*[p.get('generationId') for p in row.get('participants',[])]] if value})
    generated = {row['id']:row for row in connection.execute('SELECT * FROM generation_jobs WHERE id=ANY(%s)',(ids,)).fetchall()} if ids else {}
    result = []
    for row in rows:
        plan = by_id.get(row['plan_id'])
        image = next((asset for asset in plan.kimono.images if asset.kind == 'PRODUCT'), None) if plan else None
        if plan and plan.kimono.id!=row['kimono_id']:
            from app.modules.catalog.queries import KIMONO_SQL
            garment=connection.execute('SELECT '+KIMONO_SQL+' AS kimono FROM kimonos k WHERE k.id=%s AND k.active',(row['kimono_id'],)).fetchone()
            image=next((Asset.model_validate(a) for a in garment['kimono']['images'] if a['kind']=='PRODUCT'),None) if garment else None
        image_source='PRODUCT' if image else 'UNAVAILABLE'
        generation_status='NOT_GENERATED'
        generation=generated.get(row.get('generation_id')) or next((generated.get(UUID(p['generationId'])) for p in row.get('participants',[]) if p.get('generationId')),None)
        if row.get('generation_id') or generation:
            generation_status='UNAVAILABLE'
        outfits = [(p['kimonoId'],p.get('beltId')) for p in row.get('participants',[])] or [(row['kimono_id'],None)]
        if any(generation_matches_outfit(generation,row['user_id'],kimono,belt) for kimono,belt in outfits):
            from app.modules.try_on.service import result_url
            url=result_url(generation)
            if url:
                image=Asset(id=generation['id'],kind='GENERATION',url=url,alt={'zh-Hant':'AI 生成的和服試穿風格預覽'})
                image_source='GENERATION';generation_status='AVAILABLE'
            else:
                generation_status='DELETED' if generation['status']=='DELETED' else 'EXPIRED'
        people=row.get('participants') or []
        if not people:
            garment=connection.execute('SELECT gender FROM kimonos WHERE id=%s',(row['kimono_id'],)).fetchone()
            people=[{'id':'guest_1','role':garment['gender'] if garment else 'FEMALE','kimonoId':row['kimono_id'],'beltId':None,'generationId':row.get('generation_id')}]
        price=None
        if plan:
            from app.modules.catalog.rules import selected_belts
            price=plan.base_price if plan.kind=='COUPLE' else len(people)*plan.base_price
            for person in people:
                ids=[UUID(person['beltId'])] if person.get('beltId') else []
                try: price+=sum(belt['price'] for belt in selected_belts(connection,person['role'],ids))
                except HTTPException: price=None;break
        result.append(Look(name=plan.name.get('zh-Hant','') if plan else '已下架方案',
                           image_url=image.url if image else None,price=price,participants=people,
                           look_id=row['id'], plan_id=row['plan_id'], kimono_id=row['kimono_id'],
                           version=row['version'], available=bool(plan),
                           unavailable_reason=None if plan else 'PLAN_UNAVAILABLE',
                           current_price=price, image=image,
                           image_source=image_source, plan=plan,generation_id=row.get('generation_id'),generation_status=generation_status))
    return result


def create_look(selection, member, connection, response, idempotency_key):
    validate_selection(selection, connection, member, require_package=True)
    fingerprint = selection.fingerprint()
    if idempotency_key:
        existing = connection.execute('SELECT * FROM looks WHERE user_id = %s AND idempotency_key = %s',
                                      (member, idempotency_key)).fetchone()
        if existing:
            if existing['request_hash'] != fingerprint:
                conflict('同一次收藏請求的內容不一致，請重新操作。')
            response.status_code = 200
            return hydrate([existing], connection)[0]
    row = connection.execute('''INSERT INTO looks
        (id, user_id, plan_id, kimono_id, configuration_hash, idempotency_key, request_hash,generation_id,participants)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING *''',
        (uuid4(), member, selection.plan_id, selection.kimono_id, fingerprint, idempotency_key, fingerprint,selection.generation_id,Jsonb([p.model_dump(mode='json',by_alias=True) for p in selection.participants]))).fetchone()
    if not row:
        row = connection.execute('''SELECT * FROM looks WHERE user_id = %s
            AND (configuration_hash = %s OR idempotency_key = %s) ORDER BY (idempotency_key = %s) DESC NULLS LAST LIMIT 1''',
            (member, fingerprint, idempotency_key, idempotency_key)).fetchone()
        if not row or (row['idempotency_key'] == idempotency_key and idempotency_key and row['request_hash'] != fingerprint):
            conflict('收藏請求衝突，請重新操作。')
        response.status_code = 200
    return hydrate([row], connection)[0]


def list_looks(member, connection, page, page_size, plan_id):
    where, params = ' WHERE user_id = %s', [member]
    if plan_id:
        where += ' AND plan_id = %s'
        params.append(plan_id)
    total = connection.execute('SELECT count(*) AS total FROM looks' + where, params).fetchone()['total']
    rows = connection.execute('SELECT * FROM looks' + where + ' ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s',
                              [*params, page_size, page * page_size]).fetchall()
    return {'data': hydrate(rows, connection), 'total': total, 'next_page': page + 1 if (page + 1) * page_size < total else None}


def get_look(look_id, member, connection):
    row = connection.execute('SELECT * FROM looks WHERE id = %s AND user_id = %s', (look_id, member)).fetchone()
    if not row:
        missing()
    return hydrate([row], connection)[0]


def update_look(look_id, selection, member, connection):
    existing = connection.execute('SELECT * FROM looks WHERE id = %s AND user_id = %s FOR UPDATE', (look_id, member)).fetchone()
    if not existing:
        missing()
    if existing['version'] != selection.version:
        conflict()
    validate_selection(selection, connection, member, require_package=True)
    try:
        with connection.transaction():
            row = connection.execute('''UPDATE looks SET plan_id=%s, kimono_id=%s,
                configuration_hash=%s, generation_id=%s, participants=%s, version=version+1, updated_at=now() WHERE id=%s AND user_id=%s RETURNING *''',
                (selection.plan_id, selection.kimono_id, selection.fingerprint(),selection.generation_id,Jsonb([p.model_dump(mode='json',by_alias=True) for p in selection.participants]), look_id, member)).fetchone()
    except psycopg.errors.UniqueViolation:
        conflict('相同搭配已在收藏中，請保留原收藏。')
    return hydrate([row], connection)[0]


def delete_look(look_id, member, connection):
    row = connection.execute('DELETE FROM looks WHERE id = %s AND user_id = %s RETURNING id', (look_id, member)).fetchone()
    if not row:
        missing()
    return {'ok': True}


def compare_looks(selection, member, connection):
    if len(set(selection.look_ids)) != len(selection.look_ids):
        raise HTTPException(422, {'code': 'DUPLICATE_LOOK', 'message': '請選擇不同收藏。'})
    rows = connection.execute('SELECT * FROM looks WHERE user_id = %s AND id = ANY(%s)', (member, selection.look_ids)).fetchall()
    if len(rows) != len(selection.look_ids):
        missing()
    if len({row['kimono_id'] for row in rows}) != len(rows):
        raise HTTPException(422, {'code': 'DUPLICATE_KIMONO', 'message': '比較時請選擇不同和服方案。'})
    by_id = {row['id']: row for row in rows}
    result = hydrate([by_id[look_id] for look_id in selection.look_ids], connection)
    if not all(look.available for look in result):
        conflict('部分方案目前無法選用，請返回收藏重新選擇。')
    return result
