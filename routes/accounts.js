const express = require('express');
const router = express.Router();
const auth = require('../middleware/auth');
const db = require('../db');
const { resolveAccount, createTransferRecipient, listBanks, initiateTransfer } = require('../utils/paystack');
const { debitWallet, generateReference } = require('../utils/helpers');

router.get('/banks', auth, (_, res) => {
  (async () => {
    try {
      const banks = await listBanks();
      res.json(banks);
    } catch (err) {
      console.error(err);
      res.status(500).json({ error: 'Could not fetch bank list' });
    }
  })();
});

router.post('/link', auth, (req, res) => {
  (async () => {
    try {
      const { account_number, bank_code } = req.body;
      if (!account_number || !bank_code) return res.status(400).json({ error: 'account_number and bank_code required' });
      const resolve = await resolveAccount(account_number, bank_code);
      const recipient = await createTransferRecipient(account_number, bank_code, resolve.account_name);
      db.prepare('INSERT INTO linked_accounts (user_id, bank_code, bank_name, account_number, account_name, recipient_code) VALUES (?, ?, ?, ?, ?, ?)').run(req.user.id, bank_code, resolve.bank_name || bank_code, account_number, resolve.account_name, recipient.recipient_code);
      res.json({ message: 'Account linked successfully', account: { account_number, account_name: resolve.account_name, bank_name: resolve.bank_name, recipient_code: recipient.recipient_code } });
    } catch (err) {
      console.error(err);
      res.status(400).json({ error: err.message || 'Could not link account' });
    }
  })();
});

router.get('/linked', auth, (req, res) => {
  const accounts = db.prepare('SELECT * FROM linked_accounts WHERE user_id = ?').all(req.user.id);
  res.json(accounts);
});

router.post('/withdraw', auth, (req, res) => {
  (async () => {
    try {
      const { linked_account_id, amount, reason } = req.body;
      if (!amount || amount <= 0) return res.status(400).json({ error: 'Valid amount required' });
      let recipientCode, description;
      if (linked_account_id) {
        const acct = db.prepare('SELECT * FROM linked_accounts WHERE id = ? AND user_id = ?').get(linked_account_id, req.user.id);
        if (!acct) return res.status(404).json({ error: 'Linked account not found' });
        recipientCode = acct.recipient_code;
        description = `Withdraw to ${acct.account_number}`;
      } else {
        const { account_number, bank_code, account_name } = req.body;
        if (!account_number || !bank_code) return res.status(400).json({ error: 'account_number and bank_code required' });
        let finalName = account_name;
        if (!finalName) { const resolve = await resolveAccount(account_number, bank_code); finalName = resolve.account_name; }
        const recipient = await createTransferRecipient(account_number, bank_code, finalName);
        recipientCode = recipient.recipient_code;
        description = `Withdraw to ${account_number}`;
      }
      const transfer = await initiateTransfer(amount, recipientCode, reason || 'Wallet withdrawal');
      if (transfer.status === 'otp') {
        const ref = generateReference('withdrawal');
        db.prepare('INSERT INTO transactions (user_id, type, amount, reference, status, description, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)').run(req.user.id, 'debit', amount, ref, 'pending_otp', description, JSON.stringify({ transfer_code: transfer.transfer_code }));
        return res.json({ message: 'OTP required', requires_otp: true, transfer_code: transfer.transfer_code, reference: ref });
      }
      const ref = transfer.reference || generateReference('withdrawal');
      const newBalance = debitWallet(req.user.id, amount, ref, description);
      res.json({ message: 'Withdrawal successful', reference: ref, new_balance: newBalance });
    } catch (err) {
      console.error(err);
      res.status(400).json({ error: err.message || 'Withdrawal failed' });
    }
  })();
});

module.exports = router;
