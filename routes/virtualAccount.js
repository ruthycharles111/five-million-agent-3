const express = require('express');
const router = express.Router();
const auth = require('../middleware/auth');
const db = require('../db');
const { createCustomer, createDedicatedVirtualAccount } = require('../utils/paystack');

router.post('/create', auth, (req, res) => {
  (async () => {
    try {
      const existing = db.prepare('SELECT * FROM virtual_accounts WHERE user_id = ?').get(req.user.id);
      if (existing && existing.assigned) return res.json({ message: 'Virtual account already exists', account: existing });
      const user = db.prepare('SELECT email, first_name, last_name, phone FROM users WHERE id = ?').get(req.user.id);
      const customer = await createCustomer(user.email, user.first_name || '', user.last_name || '', user.phone || '');
      const dedicated = await createDedicatedVirtualAccount(customer.customer_code);
      db.prepare('INSERT OR REPLACE INTO virtual_accounts (user_id, customer_code, account_name, account_number, bank_name, assigned) VALUES (?, ?, ?, ?, ?, 1)').run(req.user.id, customer.customer_code, dedicated.account_name, dedicated.account_number, dedicated.bank.name);
      res.json({ message: 'Virtual account created', account: { account_name: dedicated.account_name, account_number: dedicated.account_number, bank_name: dedicated.bank.name } });
    } catch (err) {
      console.error(err);
      res.status(400).json({ error: err.message || 'Could not create virtual account' });
    }
  })();
});

router.get('/', auth, (req, res) => {
  const va = db.prepare('SELECT * FROM virtual_accounts WHERE user_id = ?').get(req.user.id);
  if (!va) return res.status(404).json({ error: 'No virtual account found. Create one.' });
  res.json(va);
});

module.exports = router;
