const db = require('../db');

function getUserWallet(userId) {
  return db.prepare('SELECT * FROM wallets WHERE user_id = ?').get(userId);
}

function creditWallet(userId, amount, reference, description = 'Wallet top-up') {
  const wallet = getUserWallet(userId);
  if (!wallet) throw new Error('Wallet not found');
  const newBalance = wallet.balance + amount;
  db.prepare('UPDATE wallets SET balance = ? WHERE user_id = ?').run(newBalance, userId);
  db.prepare('INSERT INTO transactions (user_id, type, amount, reference, status, description) VALUES (?, ?, ?, ?, ?, ?)').run(userId, 'credit', amount, reference, 'success', description);
  return newBalance;
}

function debitWallet(userId, amount, reference, description = 'Wallet debit') {
  const wallet = getUserWallet(userId);
  if (!wallet || wallet.balance < amount) throw new Error('Insufficient balance');
  const newBalance = wallet.balance - amount;
  db.prepare('UPDATE wallets SET balance = ? WHERE user_id = ?').run(newBalance, userId);
  db.prepare('INSERT INTO transactions (user_id, type, amount, reference, status, description) VALUES (?, ?, ?, ?, ?, ?)').run(userId, 'debit', amount, reference, 'success', description);
  return newBalance;
}

function generateReference(prefix = 'ajo') {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;
}

module.exports = { getUserWallet, creditWallet, debitWallet, generateReference };
