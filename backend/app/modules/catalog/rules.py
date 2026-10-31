from app.modules.catalog.queries import PLAN_FROM, PLAN_SELECT, PUBLIC_PLAN
from fastapi import HTTPException


def invalid(code,message):
    raise HTTPException(422,{'code':code,'message':message})


def selected_belts(connection,gender,ids):
    if not ids: return []
    if gender!='FEMALE' or len(ids)!=1:
        invalid('INVALID_ACCESSORY','僅女生可選一條收費腰帶。')
    rows=connection.execute("SELECT id,name,price FROM accessories WHERE id=ANY(%s) AND active AND category='BELT' FOR SHARE",(ids,)).fetchall()
    if len(rows)!=len(ids): invalid('INVALID_ACCESSORY','腰帶已下架或不存在。')
    return rows


def validate_packages(guests,plans):
    for plan_id in {p['id'] for p in plans if p}:
        group=[g for g,p in zip(guests,plans) if p and p['id']==plan_id]
        kind=next(p.get('kind','SINGLE') for p in plans if p and p['id']==plan_id)
        if kind=='COUPLE' and (len(group)!=2 or sorted(g.guest_type for g in group)!=['ADULT_FEMALE','ADULT_MALE']):
            invalid('INVALID_COUPLE','情侶方案限定兩人，需一位女生與一位男生。')
        if kind=='GROUP' and not 2<=len(group)<=3:
            invalid('INVALID_GROUP','團體方案限 2～3 人。')
        if kind=='SINGLE' and len(group)!=1:
            invalid('INVALID_SINGLE','單人方案限一位旅客。')


def pricing_lines(guests,plans):
    validate_packages(guests,plans)
    counts={};lines=[]
    for i,(guest,p) in enumerate(zip(guests,plans)):
        count=counts.get(p['id'],0);counts[p['id']]=count+1
        amount=p['base_price']
        if p.get('kind')=='COUPLE':
            amount=p['base_price'] if count==0 else 0
        lines.append({'guestIndex':i,'planId':str(p['id']),'kimonoId':str(guest.kimono_id),
            'name':p['name'],'label':('情侶套餐（兩人）' if count==0 else '套餐第二位（已含）') if p.get('kind')=='COUPLE' else '團體方案（每人）' if p.get('kind')=='GROUP' else '單人方案',
            'unitPrice':amount,'quantity':1,'total':amount,'amount':amount})
        for belt in p.get('belts',[]):
            lines.append({'guestIndex':i,'accessoryId':str(belt['id']),'name':belt['name'],'label':belt['name'],
                'unitPrice':belt['price'],'quantity':1,'total':belt['price'],'amount':belt['price']})
    return lines


def generation_matches_outfit(generation, member, kimono_id, belt_id=None):
    return bool(generation and generation['user_id']==member and generation['source']=='WEBSITE'
        and str(generation['kimono_id'])==str(kimono_id)
        and str(generation.get('belt_id') or '')==str(belt_id or ''))


def validate_selection(selection, connection, member=None, require_package=False):
    if selection.generation_id:
        generation=connection.execute("SELECT * FROM generation_jobs WHERE id=%s AND user_id=%s AND source='WEBSITE' AND status='SUCCEEDED' AND expires_at>now()",(selection.generation_id,member)).fetchone() if member else None
        belt_id = selection.participants[0].belt_id if selection.participants else None
        if not generation_matches_outfit(generation,member,selection.kimono_id,belt_id):
            raise HTTPException(422,{'code':'INVALID_GENERATION','message':'此生成圖不屬於你、已到期，或與目前搭配不符。'})
    row = connection.execute(PLAN_SELECT + PLAN_FROM + ' WHERE ' + PUBLIC_PLAN + ' AND p.id = %s', (selection.plan_id,)).fetchone()
    if not row:
        raise HTTPException(422, {'code': 'PLAN_UNAVAILABLE', 'message': '此方案目前無法收藏，請重新選擇。'})
    garment = connection.execute('SELECT id,gender FROM kimonos WHERE id=%s AND active',(selection.kimono_id,)).fetchone()
    if not garment:
        raise HTTPException(422, {'code':'INVALID_OUTFIT','message':'和服已無法選用。'})
    if require_package and not selection.participants and row.get('kind') in ('COUPLE','GROUP'):
        invalid('INVALID_GUEST_COUNT','請提供此多人方案的完整旅客搭配。')
    if selection.participants:
        from app.modules.catalog.rules import selected_belts
        from types import SimpleNamespace
        from app.modules.catalog.rules import validate_packages
        guests=[];plans=[]
        for person in selection.participants:
            item=connection.execute('SELECT gender FROM kimonos WHERE id=%s AND active',(person.kimono_id,)).fetchone()
            if not item or item['gender']!=person.role:
                raise HTTPException(422,{'code':'INVALID_OUTFIT','message':'和服與旅客角色不符。'})
            selected_belts(connection,person.role,[person.belt_id] if person.belt_id else [])
            if person.generation_id:
                generated=connection.execute("SELECT * FROM generation_jobs WHERE id=%s AND user_id=%s AND status='SUCCEEDED' AND expires_at>now()",(person.generation_id,member)).fetchone()
                if not generation_matches_outfit(generated,member,person.kimono_id,person.belt_id):
                    raise HTTPException(422,{'code':'INVALID_GENERATION','message':'生成圖與本人和服、腰帶搭配不符或已到期。'})
            guests.append(SimpleNamespace(guest_type='ADULT_'+person.role))
            plans.append({'id':row['id'],'kind':row.get('kind','SINGLE')})
        validate_packages(guests,plans)

    if selection.accessory_ids:
        from app.modules.catalog.rules import selected_belts
        selected_belts(connection, garment['gender'], selection.accessory_ids)
