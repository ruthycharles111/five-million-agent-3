const express = require('express');
const router = express.Router();
const auth = require('../middleware/auth');
const db = require('../db');
const { createTransferRecipient, initiateTransfer, finalizeTransfer, resolveAccount } = require('../utils/paystack');
const { debitWallet, creditWallet, generateReference } = require('../utils/helpers');

router.post('/internal', auth, (req, res) => {
  try {
    const { recipientEmail, amount } = req.body;
    if (!recipientEmail || !amount || amount <= 0) return res.status(400).json({ error: 'Recipient email and valid amount required' });
    const recipient = db.prepare('SELECT id, email FROM users WHERE email = ?').get(recipientEmail);
    if (!recipient) return res.status(404).json({ error: 'Recipient not found' });
    if (recipient.id === req.user.id) return res.status(400).json({ error: 'Cannot send to yourself' });
    const ref = generateReference('internal_transfer');
    const newSenderBalance = debitWallet(req.user.id, amount, ref, `Sent to ${recipient.email}`);
    const recipientRef = generateReference('internal_credit');
    creditWallet(recipient.id, amount, recipientRef, `Received from user ${req.user.id}`);
    res.json({ message: 'Transfer successful', reference: ref, new_balance: newSenderBalance });
  } catch (err) {
    console.error(err);
    res.status(400).json({ error: err.message });
  }
});

router.post('/bank', auth, (req, res) => {
  (async () => {
    try {
      const { account_number, bank_code, account_name, amount, reason } = req.body;
      if (!account_number || !bank_code || !amount || amount <= 0) return res.status(400).json({ error: 'account_number, bank_code, and valid amount required' });
      let finalAccountName = account_name;
      if (!finalAccountName) {
        const resolveData = await resolveAccount(account_number, bank_code);
        finalAccountName = resolveData.account_name;
      }
      const recipient = await createTransferRecipient(account_number, bank_code, finalAccountName);
      const transfer = await initiateTransfer(amount, recipient.recipient_code, reason || 'Bank transfer');
      if (transfer.status === 'otp') {
        const ref = generateReference('bank_transfer');
        db.prepare('INSERT INTO transactions (user_id, type, amount, reference, status, description, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)').run(req.user.id, 'debit', amount, ref, 'pending_otp', 'Bank transfer - OTP required', JSON.stringify({ transfer_code: transfer.transfer_code, recipient_code: recipient.recipient_code }));
        return res.json({ message: 'OTP required to complete transfer', requires_otp: true, reference: ref, transfer_code: transfer.transfer_code });
      }
      const ref = transfer.reference || generateReference('bank_transfer');
      const newBalance = debitWallet(req.user.id, amount, ref, `Bank transfer to ${account_number}`);
      res.json({ message: 'Transfer completed', reference: ref, new_balance: newBalance });
    } catch (err) {
      console.error(err);
      res.status(400).json({ error: err.message || 'Transfer failed' });
    }
  })();
});

router.post('/bank/otp', auth, (req, res) => {
  (async () => {
    try {
      const { transfer_code, otp } = req.body;
      if (!transfer_code || !otp) return res.status(400).json({ error: 'transfer_code and otp required' });
      const result = await finalizeTransfer(transfer_code, otp);
      const tx = db.prepare("SELECT * FROM transactions WHERE user_id = ? AND status = 'pending_otp' AND metadata LIKE ?").get(req.user.id, `%${transfer_code}%`);
      if (tx) {
        db.prepare('UPDATE transactions SET status = ? WHERE id = ?').run('success', tx.id);
        const wallet = db.prepare('SELECT * FROM wallets WHERE user_id = ?').get(req.user.id);
        const newBalance = wallet.balance - tx.amount;
        if (newBalance < 0) throw new Error('Insufficient balance after OTP');
        db.prepare('UPDATE wallets SET balance = ? WHERE user_id = ?').run(newBalance, req.user.id);
      }
      res.json({ message: 'Transfer completed via OTP', status: result.status });
    } catch (err) {
      console.error(err);
      res.status(400).json({ error: err.message || 'OTP finalization failed' });
    }
  })();
});

module.exports = router;
