/*
    Code taken from:
    https://www.linux.org/threads/c-tutorial-create-qt-applications-without-qtcreator.18409/ 
*/
#ifndef MAINWIDGET_H
#define MAINWIDGET_H

#include <QWidget>

class QPushButton;
class QTextBrowser;

class MainWidget : public QWidget
{
    Q_OBJECT

public:
    explicit MainWidget(QWidget *parent = 0); //Constructor
    ~MainWidget(); // Destructor

private:
   QPushButton* button_;
   QTextBrowser* textBrowser_;
};

#endif // MAINWIDGET_H

