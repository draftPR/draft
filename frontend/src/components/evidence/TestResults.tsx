import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { CheckCircle, XCircle, Clock, AlertCircle } from 'lucide-react';
import type { TestResult } from '../../hooks/useTicketEvidence';

interface TestResultsProps {
  results: TestResult[];
}

export function TestResults({ results }: TestResultsProps) {
  const [expandedTests, setExpandedTests] = useState<Set<string>>(new Set());

  const toggleTest = (testName: string) => {
    setExpandedTests(prev => {
      const next = new Set(prev);
      if (next.has(testName)) {
        next.delete(testName);
      } else {
        next.add(testName);
      }
      return next;
    });
  };

  if (!results || results.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No test results available
        </CardContent>
      </Card>
    );
  }

  const passed = results.filter(r => r.status === 'passed').length;
  const failed = results.filter(r => r.status === 'failed').length;
  const skipped = results.filter(r => r.status === 'skipped').length;
  const totalDuration = results.reduce((sum, r) => sum + r.duration_ms, 0);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'passed':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" />;
      case 'skipped':
        return <Clock className="h-4 w-4 text-gray-400" />;
      default:
        return <AlertCircle className="h-4 w-4 text-yellow-500" />;
    }
  };

  const getStatusBadge = (status: string) => {
    const config = {
      passed: { variant: 'default', className: 'bg-green-500' },
      failed: { variant: 'destructive', className: '' },
      skipped: { variant: 'secondary', className: '' },
    };
    return config[status as keyof typeof config] || config.skipped;
  };

  return (
    <div className="space-y-4">
      {/* Summary */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Test Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-4 gap-4">
            <div className="space-y-1">
              <div className="text-2xl font-bold">{results.length}</div>
              <div className="text-xs text-muted-foreground">Total Tests</div>
            </div>
            <div className="space-y-1">
              <div className="text-2xl font-bold text-green-500">{passed}</div>
              <div className="text-xs text-muted-foreground">Passed</div>
            </div>
            <div className="space-y-1">
              <div className="text-2xl font-bold text-red-500">{failed}</div>
              <div className="text-xs text-muted-foreground">Failed</div>
            </div>
            <div className="space-y-1">
              <div className="text-2xl font-bold text-gray-500">{skipped}</div>
              <div className="text-xs text-muted-foreground">Skipped</div>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t">
            <div className="text-sm text-muted-foreground">
              Total duration: <span className="font-mono">{(totalDuration / 1000).toFixed(2)}s</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Individual test results */}
      <div className="space-y-2">
        {results.map((test, idx) => {
          const isExpanded = expandedTests.has(test.name);
          const badgeConfig = getStatusBadge(test.status);

          return (
            <Card
              key={idx}
              className={`cursor-pointer transition-colors hover:bg-accent ${
                test.status === 'failed' ? 'border-red-200 dark:border-red-800' : ''
              }`}
              onClick={() => toggleTest(test.name)}
            >
              <CardContent className="pt-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2">
                      {getStatusIcon(test.status)}
                      <span className="font-mono text-sm">{test.name}</span>
                    </div>

                    {isExpanded && (test.output || test.error) && (
                      <div className="space-y-2">
                        {test.output && (
                          <div>
                            <div className="text-xs font-semibold text-muted-foreground mb-1">
                              Output:
                            </div>
                            <pre className="rounded bg-secondary p-2 text-xs font-mono overflow-x-auto">
                              {test.output}
                            </pre>
                          </div>
                        )}
                        {test.error && (
                          <div>
                            <div className="text-xs font-semibold text-red-500 mb-1">Error:</div>
                            <pre className="rounded bg-red-100 dark:bg-red-950 p-2 text-xs font-mono overflow-x-auto text-red-900 dark:text-red-100">
                              {test.error}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground font-mono">
                      {(test.duration_ms / 1000).toFixed(2)}s
                    </span>
                    <Badge variant={badgeConfig.variant as any} className={badgeConfig.className}>
                      {test.status}
                    </Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {failed > 0 && (
        <Card className="bg-red-50 dark:bg-red-950 border-red-200 dark:border-red-800">
          <CardContent className="pt-4">
            <div className="flex items-start gap-2">
              <XCircle className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
              <div className="space-y-1">
                <p className="text-sm font-semibold text-red-900 dark:text-red-100">
                  {failed} test{failed > 1 ? 's' : ''} failed
                </p>
                <p className="text-sm text-red-800 dark:text-red-200">
                  Click on failed tests above to view error details. The ticket should not be
                  merged until all tests pass.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {passed === results.length && (
        <Card className="bg-green-50 dark:bg-green-950 border-green-200 dark:border-green-800">
          <CardContent className="pt-4">
            <div className="flex items-start gap-2">
              <CheckCircle className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-green-900 dark:text-green-100">
                <strong>All tests passed!</strong> The changes have been verified and are safe to
                merge.
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
