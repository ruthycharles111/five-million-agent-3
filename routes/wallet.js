const express = require('express');
const router = express.Router();
const auth = require('../middleware/auth');
const { initializePayment } = require('../utils/paystack');
const { generateReference, creditWallet } = require('../utils/helpers');
const db = require('../db');

router.get('/balance', auth, (req, res) => {
  const wallet = db.prepare('SELECT * FROM wallets WHERE user_id = ?').get(req.user.id);
  if (!wallet) return res.status(404).json({ error: 'Wallet not found' });
  res.json({ balance: wallet.balance, currency: wallet.currency });
});

router.post('/fund', auth, (req, res) => {
  try {
    const { amount, callback_url } = req.body;
    if (!amount || amount <= 0) return res.status(400).json({ error: 'Valid amount required' });
    const reference = generateReference('fund');
    const user = db.prepare('SELECT email FROM users WHERE id = ?').get(req.user.id);
    initializePayment(user.email, amount, callback_url || 'https://yourapp.com/callback')
      .then(data => {
        db.prepare('INSERT INTO transactions (user_id, type, amount, reference, status, description) VALUES (?, ?, ?, ?, ?, ?)').run(req.user.id, 'credit', amount, reference, 'pending', 'Wallet funding');
        res.json({ authorization_url: data.authorization_url, reference });
      })
      .catch(err => {
        console.error(err);
        res.status(500).json({ error: 'Payment initialization failed', details: err.message });
      });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

module.exports = router;
