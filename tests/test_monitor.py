import importlib.util
import unittest


class MonitorBehavior(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('monitor'), 'Local stock monitor has not been implemented')
        import monitor
        self.m = monitor
        self.product = {'alias':'amul-high-protein-plain-lassi-200-ml-or-pack-of-30','sku':'LASCP61_30','name':'Plain lassi','available':0,'publish':'1','inventory_quantity':5,'price':900}

    def test_positive_quantity_does_not_override_unavailable(self):
        self.assertEqual(self.m.classify(self.product, self.product['alias'], 'LASCP61_30')['status'], 'out_of_stock')

    def test_missing_availability_and_wrong_identity_are_unknown(self):
        for changes in [{'available':None},{'alias':'different-product'},{'sku':'different-pack'},{'publish':'0'},{'available':'unexpected'}]:
            self.assertEqual(self.m.classify(self.product | changes, self.product['alias'], 'LASCP61_30')['status'], 'unknown')

    def test_explicit_available_product_is_reported(self):
        self.assertEqual(self.m.classify(self.product | {'available':1}, self.product['alias'], 'LASCP61_30')['status'], 'available')

    def test_initial_stock_alert_is_not_repeated_after_unknown(self):
        state = {}; sent=[]
        for status in ['available','available','unknown','available']:
            self.m.process(state, {'plain':{'status':status}}, sent.append)
        self.assertEqual([e['kind'] for e in sent], ['restock'])

    def test_later_restock_alerts_again(self):
        state = {}; sent=[]
        for status in ['out_of_stock','available','out_of_stock','available']:
            self.m.process(state, {'plain':{'status':status}}, sent.append)
        self.assertEqual([e['kind'] for e in sent], ['restock','restock'])

    def test_new_pin_does_not_inherit_previous_location_alert_history(self):
        state={'pin':'999999','products':{'plain':{'last_confirmed':'available'}},'health_warned':True,'consecutive_errors':3}
        sent=[]
        self.m.process(state, {'plain':{'status':'available'}}, sent.append)
        self.assertEqual([e['kind'] for e in sent], ['restock'])

    def test_new_pin_starts_a_new_error_count(self):
        state={'pin':'999999','consecutive_errors':2};sent=[]
        self.m.process(state, {'plain':{'status':'unknown'}}, sent.append)
        self.assertEqual(sent,[])
        self.assertEqual(state['consecutive_errors'],1)

    def test_notification_failure_retries_without_losing_restock(self):
        state = {}; sent=[]
        def fail(event): raise RuntimeError('notification unavailable')
        with self.assertRaises(RuntimeError): self.m.process(state, {'plain':{'status':'available'}}, fail)
        self.m.process(state, {'plain':{'status':'available'}}, sent.append)
        self.assertEqual([e['kind'] for e in sent], ['restock'])

    def test_warn_once_after_three_errors_then_report_recovery(self):
        state = {}; sent=[]
        for _ in range(5): self.m.process(state, {'plain':{'status':'unknown','reason':'HTTP error'}}, sent.append)
        self.assertEqual([e['kind'] for e in sent], ['health'])
        self.m.process(state, {'plain':{'status':'out_of_stock'}}, sent.append)
        self.assertEqual([e['kind'] for e in sent], ['health','recovery'])

    def test_products_are_tracked_independently(self):
        state = {}; sent=[]
        self.m.process(state, {'plain':{'status':'available'},'rose':{'status':'out_of_stock'}}, sent.append)
        self.m.process(state, {'plain':{'status':'available'},'rose':{'status':'available'}}, sent.append)
        self.assertEqual([e['product'] for e in sent], ['plain','rose'])

    def test_failed_rose_alert_does_not_hide_plain_restock(self):
        state = {}; sent=[]
        self.m.process(state, {'rose':{'status':'out_of_stock'},'plain':{'status':'available'}}, sent.append)
        def fail(event): raise RuntimeError('notification unavailable')
        with self.assertRaises(RuntimeError):
            self.m.process(state, {'rose':{'status':'available'},'plain':{'status':'out_of_stock'}}, fail)
        sent.clear()
        self.m.process(state, {'rose':{'status':'available'},'plain':{'status':'available'}}, sent.append)
        self.assertEqual([e['product'] for e in sent], ['rose','plain'])


if __name__ == '__main__': unittest.main()
