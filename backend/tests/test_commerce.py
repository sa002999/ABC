import unittest
from types import SimpleNamespace
from uuid import uuid4
from fastapi import HTTPException
from pydantic import ValidationError
from bookings import Guest
from commerce import pricing_lines, selected_belts


class CommerceTests(unittest.TestCase):
    def test_couple_third_guest_and_belts(self):
        plan_id=uuid4();kimono_id=uuid4();belt_id=uuid4()
        guests=[SimpleNamespace(guest_type='ADULT_FEMALE',kimono_id=kimono_id),SimpleNamespace(guest_type='ADULT_MALE',kimono_id=kimono_id),SimpleNamespace(guest_type='ADULT_FEMALE',kimono_id=kimono_id)]
        plan={'id':plan_id,'name':{'zh-Hant':'情侶'},'kind':'COUPLE','base_price':2800,'additional_guest_price':1500}
        plans=[{**plan,'belts':[{'id':belt_id,'name':'腰帶','price':200}]},plan,plan]
        lines=pricing_lines(guests,plans)
        self.assertEqual(sum(l['total'] for l in lines),4500)
        self.assertEqual([l['total'] for l in lines if 'planId' in l],[2800,0,1500])
        with self.assertRaises(HTTPException): pricing_lines(guests[:1],plans[:1])
        with self.assertRaises(HTTPException): pricing_lines([guests[0],guests[0]],plans[:2])

    def test_no_child_no_male_belt_and_no_unknown_belt(self):
        with self.assertRaises(ValidationError): Guest(guestType='CHILD')
        with self.assertRaises(HTTPException): Guest(guestType='ADULT_MALE',accessoryIds=[uuid4()])
        with self.assertRaises(HTTPException): selected_belts(None,'MALE',[uuid4()])
        class Empty:
            def execute(self,*args): return self
            def fetchall(self): return []
        with self.assertRaises(HTTPException): selected_belts(Empty(),'FEMALE',[uuid4()])
