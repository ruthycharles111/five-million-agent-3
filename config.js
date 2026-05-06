require('dotenv').config();
module.exports = {
  port: process.env.PORT || 3000,
  paystackSecretKey: process.env.PAYSTACK_SECRET_KEY,
  jwtSecret: process.env.JWT_SECRET || 'default_jwt_secret_replace_me',
  serverIp: process.env.SERVER_IP || '102.89.0.0',
};
