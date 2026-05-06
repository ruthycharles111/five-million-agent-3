const Paystack = require('paystack')(process.env.PAYSTACK_SECRET_KEY);
const axios = require('axios');
const PAYSTACK_BASE = 'https://api.paystack.co';
const paystackApi = axios.create({
  baseURL: PAYSTACK_BASE,
  headers: {
    Authorization: `Bearer ${process.env.PAYSTACK_SECRET_KEY}`,
    'Content-Type': 'application/json',
  },
});

async function initializePayment(email, amount, callbackUrl) {
  const response = await Paystack.transaction.initialize({
    email,
    amount: Math.round(amount * 100),
    callback_url: callbackUrl,
  });
  return response.data;
}

async function verifyTransaction(reference) {
  const response = await Paystack.transaction.verify(reference);
  return response.data;
}

async function createTransferRecipient(accountNumber, bankCode, accountName) {
  const response = await Paystack.transferrecipient.create({
    type: 'nuban',
    name: accountName,
    account_number: accountNumber,
    bank_code: bankCode,
    currency: 'NGN',
  });
  return response.data;
}

async function initiateTransfer(amount, recipientCode, reason) {
  const response = await Paystack.transfer.create({
    source: 'balance',
    amount: Math.round(amount * 100),
    recipient: recipientCode,
    reason: reason || 'Ajo Withdrawal',
  });
  return response.data;
}

async function finalizeTransfer(transferCode, otp) {
  const response = await Paystack.transfer.finalize({
    transfer_code: transferCode,
    otp,
  });
  return response.data;
}

async function resolveAccount(accountNumber, bankCode) {
  const response = await Paystack.verification.resolveAccount({
    account_number: accountNumber,
    bank_code: bankCode,
  });
  return response.data;
}

async function listBanks() {
  const response = await Paystack.misc.list_banks({ country: 'nigeria' });
  return response.data;
}

async function buyAirtime(network, phone, amount) {
  try {
    const { data } = await paystackApi.post('/airtime', {
      network: network.toLowerCase(),
      phone,
      amount: Math.round(amount * 100),
    });
    return data;
  } catch (err) {
    throw err.response?.data || err.message;
  }
}

async function getDataPlans(network) {
  try {
    const { data } = await paystackApi.get('/data/plans', {
      params: { network: network.toLowerCase() },
    });
    return data;
  } catch (err) {
    throw err.response?.data || err.message;
  }
}

async function buyData(network, phone, planCode) {
  try {
    const { data } = await paystackApi.post('/data', {
      network: network.toLowerCase(),
      phone,
      plan_code: planCode,
    });
    return data;
  } catch (err) {
    throw err.response?.data || err.message;
  }
}

async function createCustomer(email, firstName, lastName, phone) {
  const response = await Paystack.customer.create({
    email,
    first_name: firstName,
    last_name: lastName,
    phone,
  });
  return response.data;
}

async function createDedicatedVirtualAccount(customerCode) {
  const response = await Paystack.dedicatedaccount.create({
    customer: customerCode,
    preferred_bank: 'wema-bank',
  });
  return response.data;
}

module.exports = {
  initializePayment,
  verifyTransaction,
  createTransferRecipient,
  initiateTransfer,
  finalizeTransfer,
  resolveAccount,
  listBanks,
  buyAirtime,
  getDataPlans,
  buyData,
  createCustomer,
  createDedicatedVirtualAccount,
};
