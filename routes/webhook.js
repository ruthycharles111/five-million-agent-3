const express = require('express');
const crypto = require('crypto');
const router = express.Router();
const db = require('../db');
const { paystackSecretKey } = require('../config');
const { creditWallet } = require('../utils/helpers');

router.post('/paystack', (req, res) => {
  const hash = crypto.createHmac('sha512', paystackSecretKey).update(JSON.stringify(req.body)).digest('hex');
  if (hash !== req.headers['x-paystack-signature']) return res.status(401).send('Invalid signature');
  const event = req.body;
  if (event.event === 'charge.success') {
    const data = event.data;
    const reference = data.reference;
    const amount = data.amount / 100;
    const email = data.customer?.email;
    if (email) {
      const user = db.prepare('SELECT id FROM users WHERE email = ?').get(email);
      if (user) {
        const tx = db.prepare('SELECT * FROM transactions WHERE reference = ? AND status = ?').get(reference, 'success');
        if (!tx) creditWallet(user.id, amount, reference, `Payment via ${data.channel}`);
      }
    }
  }
  if (event.event === 'transfer.success') {
    const transfer = event.data;
    if (transfer.recipient && transfer.recipient.type === 'nuban') {
      const virtualAccount = db.prepare('SELECT user_id FROM virtual_accounts WHERE account_number = ?').get(transfer.recipient.account_number);
      if (virtualAccount) {
        const amount = transfer.amount / 100;
        creditWallet(virtualAccount.user_id, amount, transfer.reference, 'Incoming transfer via VA');
      }
    }
  }
  res.sendStatus(200);
});

module.exports = router;
