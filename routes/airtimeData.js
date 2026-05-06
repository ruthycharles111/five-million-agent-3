const express = require('express');
const router = express.Router();
const auth = require('../middleware/auth');
const { buyAirtime, getDataPlans, buyData } = require('../utils/paystack');
const { debitWallet, creditWallet, generateReference } = require('../utils/helpers');

router.post('/airtime', auth, (req, res) => {
  (async () => {
    try {
      const { network, phone, amount } = req.body;
      if (!network || !phone || !amount || amount <= 0) return res.status(400).json({ error: 'network, phone, and valid amount required' });
      const ref = generateReference('airtime');
      debitWallet(req.user.id, amount, ref, `Airtime ${network} ${phone}`);
      const result = await buyAirtime(network, phone, amount);
      res.json({ message: 'Airtime purchase successful', reference: ref, details: result });
    } catch (err) {
      try { creditWallet(req.user.id, amount, generateReference('refund'), 'Airtime refund'); } catch (_) {}
      console.error(err);
      res.status(400).json({ error: err.message || 'Airtime purchase failed. Amount refunded.' });
    }
  })();
});

router.get('/data/plans', auth, (req, res) => {
  (async () => {
    try {
      const { network } = req.query;
      if (!network) return res.status(400).json({ error: 'network query param required' });
      const plans = await getDataPlans(network);
      res.json(plans);
    } catch (err) {
      console.error(err);
      res.status(400).json({ error: err.message || 'Could not fetch data plans' });
    }
  })();
});

router.post('/data', auth, (req, res) => {
  (async () => {
    try {
      const { network, phone, plan_code, amount } = req.body;
      if (!network || !phone || !plan_code || !amount || amount <= 0) return res.status(400).json({ error: 'network, phone, plan_code, and valid amount required' });
      const ref = generateReference('data');
      debitWallet(req.user.id, amount, ref, `Data bundle ${network} ${plan_code}`);
      const result = await buyData(network, phone, plan_code);
      res.json({ message: 'Data purchase successful', reference: ref, details: result });
    } catch (err) {
      try { creditWallet(req.user.id, amount, generateReference('refund'), 'Data bundle refund'); } catch (_) {}
      console.error(err);
      res.status(400).json({ error: err.message || 'Data purchase failed. Amount refunded.' });
    }
  })();
});

module.exports = router;
