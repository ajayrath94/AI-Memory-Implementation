// Global error handler — logs the real JS error before native crash reporting swallows it
if (!(global as any).__errorHandlerInstalled) {
  (global as any).__errorHandlerInstalled = true
  const defaultHandler = ErrorUtils.getGlobalHandler()
  ErrorUtils.setGlobalHandler((error, isFatal) => {
    console.log('========== REAL JS ERROR ==========')
    console.log('Message:', error?.message)
    console.log('Stack:', error?.stack)
    console.log('isFatal:', isFatal)
    console.log('====================================')
    defaultHandler(error, isFatal)
  })
}
export {}
